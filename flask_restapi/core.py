import functools
from typing import Any, Dict, Type

from flask import Flask, request, make_response
from pydantic import BaseModel

from .exceptions import ValidationErrorResponses
from .mixins import AuthTokenMixin, HandlerMixin, SpecMixin
from .spec.models import BlueprintMap, TagModel
from .types import RequestParametersType


class Api(SpecMixin, AuthTokenMixin, HandlerMixin):
    def __init__(self, app: Flask = None, algorithm: str = "HS256") -> None:
        SpecMixin.__init__(self)
        AuthTokenMixin.__init__(self, algorithm)
        HandlerMixin.__init__(self)
        self.app = app
        if app is not None:
            self.init_app(app)

    def init_app(self, app: Flask) -> None:
        self.app = app

        SpecMixin._init_config(self)
        AuthTokenMixin._init_config(self)

        self.app.before_first_request(self._register_spec)
        self._register_blueprint()
        self._register_handlers()

    def bp_map(self, blueprint_name: str = None, endpoint_name: str = None):
        def decorator(cls):
            blueprint_map = BlueprintMap(
                endpoint_name=endpoint_name or cls.__name__.lower(),
                blueprint_name=blueprint_name,
            )
            self.spec.blueprint_maps.append(blueprint_map)

            return cls

        return decorator

    def header(
        self,
        schema: Type[BaseModel],
        endpoint: str = None,
        method_name: str = None,
        tag: Type[TagModel] = None,
        summary: str = None,
    ):
        def decorator(func):
            ep = endpoint if endpoint else self._generate_endpoint(func.__qualname__)
            _method_name = method_name or func.__name__
            _summary = summary or func.__doc__ or None
            self.spec.store_parameters(
                "header", schema, ep, _method_name, tag, _summary
            )

            @functools.wraps(func)
            def wrapper(func_self=None, *args, **kwargs):
                request.parameters = self._get_request_parameters()
                _headers = dict((k.lower(), v) for k, v in request.headers.items())
                request.parameters.header = schema(**_headers)
                return func(func_self, request.parameters, **kwargs)

            return wrapper

        return decorator

    def path(
        self,
        schema: Type[BaseModel],
        endpoint: str = None,
        method_name: str = None,
        tag: Type[TagModel] = None,
        summary: str = None,
    ):
        def decorator(func):
            ep = endpoint if endpoint else self._generate_endpoint(func.__qualname__)
            _method_name = method_name or func.__name__
            _summary = summary or func.__doc__ or None
            self.spec.store_parameters("path", schema, ep, _method_name, tag, _summary)

            @functools.wraps(func)
            def wrapper(func_self=None, *args, **kwargs):
                request.parameters = self._get_request_parameters()
                request.parameters.path = schema(**request.view_args)
                return func(func_self, request.parameters, **kwargs)

            return wrapper

        return decorator

    def query(
        self,
        schema: Type[BaseModel],
        endpoint: str = None,
        method_name: str = None,
        tag: Type[TagModel] = None,
        summary: str = None,
    ):
        def decorator(func):
            ep = endpoint if endpoint else self._generate_endpoint(func.__qualname__)
            _method_name = method_name or func.__name__
            _summary = summary or func.__doc__ or None
            self.spec.store_parameters("query", schema, ep, _method_name, tag, _summary)

            @functools.wraps(func)
            def wrapper(func_self=None, *args, **kwargs):
                request.parameters = self._get_request_parameters()
                request.parameters.query = schema(**request.args.to_dict())
                return func(func_self, request.parameters, **kwargs)

            return wrapper

        return decorator

    def body(
        self,
        schema: Type[BaseModel],
        endpoint: str = None,
        method_name: str = None,
        content_type: list = ["application/json"],
        tag: Type[TagModel] = None,
        summary: str = None,
    ):
        def decorator(func):
            ep = endpoint if endpoint else self._generate_endpoint(func.__qualname__)
            _method_name = method_name or func.__name__
            _summary = summary or func.__doc__ or None
            self.spec.store_body(schema, ep, _method_name, content_type, tag, _summary)

            @functools.wraps(func)
            def wrapper(func_self=None, *args, **kwargs):
                request.parameters = self._get_request_parameters()
                body: Any = request.get_json()
                request.parameters.body = schema(**body)
                return func(func_self, request.parameters, **kwargs)

            return wrapper

        return decorator

    def form(
        self,
        schema: Type[BaseModel],
        endpoint: str = None,
        method_name: str = None,
        content_type: list = ["multipart/form-data"],
        tag: Type[TagModel] = None,
        summary: str = None,
    ):
        def decorator(func):
            ep = endpoint if endpoint else self._generate_endpoint(func.__qualname__)
            _method_name = method_name or func.__name__
            _summary = summary or func.__doc__ or None
            self.spec.store_body(schema, ep, _method_name, content_type, tag, _summary)

            @functools.wraps(func)
            def wrapper(func_self=None, *args, **kwargs):
                request.parameters = self._get_request_parameters()
                _form = {}
                if request.files.to_dict():
                    _form.update(request.files.to_dict())

                if request.form.to_dict():
                    _form.update(request.form.to_dict())

                request.parameters.form = schema(**_form)
                return func(func_self, request.parameters, **kwargs)

            return wrapper

        return decorator

    def auth(self, endpoint: str = None, method_name: str = None):
        def decorator(func):
            ep = endpoint if endpoint else self._generate_endpoint(func.__qualname__)
            _method_name = method_name or func.__name__
            self.spec.store_auth(ep, _method_name)

            @functools.wraps(func)
            def wrapper(func_self=None, *args, **kwargs):
                request.parameters = self._get_request_parameters()
                auth_header = request.headers.get("Authorization")
                if auth_header is not None:
                    if "Bearer" in auth_header:
                        _token = auth_header.split(" ")[1]
                        request.parameters.auth = _token
                    else:
                        request.parameters.auth = auth_header

                return func(func_self, request.parameters, **kwargs)

            return wrapper

        return decorator

    def response(
        self,
        schema: Type[BaseModel],
        endpoint: str = None,
        method_name: str = None,
        content_type: list = ["application/json"],
        headers: Dict[str, Any] = None,
        code: int = 200,
        default_validation_error: bool = True,
    ):
        def decorator(func):
            ep = endpoint if endpoint else self._generate_endpoint(func.__qualname__)
            _method_name = method_name or func.__name__
            self.spec.store_responses(code, schema, ep, _method_name, content_type)
            if default_validation_error:
                self.spec.store_responses(
                    422, ValidationErrorResponses, ep, _method_name, content_type
                )

            @functools.wraps(func)
            def wrapper(func_self=None, *args, **kwargs):
                request.parameters = self._get_request_parameters()
                result = func(func_self, request.parameters, **kwargs)
                if isinstance(result, BaseModel):
                    response = make_response(result.dict(exclude={"headers"}), code)
                else:
                    response = make_response(result, code)

                # Add header from result
                if hasattr(result, "headers"):
                    if isinstance(result.headers, dict):
                        for key, value in result.headers.items():
                            response.headers[key] = value

                # Add header from decorator
                if isinstance(headers, dict):
                    for key, value in headers.items():
                        response.headers[key] = value

                return response

            return wrapper

        return decorator

    def _get_request_parameters(self) -> RequestParametersType:
        if not hasattr(request, "parameters"):
            request.parameters = RequestParametersType()

        return request.parameters

    def _generate_endpoint(self, endpoint: str) -> str:
        return endpoint.split(".")[0].lower()
