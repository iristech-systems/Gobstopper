"""OpenAPI metadata decorators for Gobstopper route handlers.

This module provides decorators to attach OpenAPI 3.1 metadata to route handler
functions. Decorators can be stacked to build comprehensive API documentation.

The decorators store metadata in a __openapi__ attribute on the handler function,
which is later collected by the OpenAPIGenerator during spec generation.

Available Decorators:
    - @doc: General operation metadata (summary, description, tags, etc.)
    - @response: Response specifications for different status codes
    - @request_body: Request body schema and requirements
    - @param: Additional parameters (query, header, cookie, path)
    - @security: Operation-level security requirements

Example:
    >>> from dataclasses import dataclass
    >>> from gobstopper.extensions.openapi.decorators import doc, response, request_body
    >>>
    >>> @dataclass
    >>> class User:
    ...     id: int
    ...     name: str
    >>>
    >>> @app.post("/users")
    >>> @doc(
    ...     summary="Create a new user",
    ...     description="Creates a user with the provided details",
    ...     tags=["Users"],
    ...     operationId="createUser"
    >>> )
    >>> @request_body(model=User, description="User to create", required=True)
    >>> @response(201, description="User created successfully", model=User)
    >>> @response(400, description="Invalid input")
    >>> async def create_user(request):
    ...     data = await request.json()
    ...     return JSONResponse(data, status=201)

See Also:
    OpenAPI 3.1 Operation Object: https://spec.openapis.org/oas/v3.1.0#operation-object
"""
from __future__ import annotations

from typing import Any, Callable


def _ensure_openapi_meta(func: Callable) -> dict:
    """Ensure a function has an __openapi__ metadata dictionary.

    Creates and attaches an empty dict if not present, otherwise returns existing.

    Args:
        func: The route handler function to check/modify.

    Returns:
        The __openapi__ metadata dictionary attached to the function.
    """
    meta = getattr(func, "__openapi__", None)
    if meta is None:
        meta = {}
        setattr(func, "__openapi__", meta)
    return meta


def doc(**fields):
    """Attach OpenAPI operation metadata to a route handler.

    This decorator allows you to specify arbitrary OpenAPI Operation Object fields
    that will be included in the generated OpenAPI specification. Common fields
    include summary, description, tags, operationId, and deprecated.

    All OpenAPI 3.1 operation fields are supported, including extension fields
    (x-*), callbacks, servers, and externalDocs.

    Args:
        **fields: OpenAPI operation fields as keyword arguments. Common fields:
            - summary (str): Short summary of the operation.
            - description (str): Detailed description (Markdown supported).
            - tags (list[str]): List of tags for grouping operations.
            - operationId (str): Unique identifier for the operation.
            - deprecated (bool): Whether the operation is deprecated.
            - externalDocs (dict): External documentation reference.
            - callbacks (dict): Callback definitions.
            - servers (list[dict]): Operation-specific server overrides.
            - x-* (Any): Custom extension fields.

    Returns:
        Decorator function that attaches metadata to the handler.

    Example:
        Basic usage::

            @app.get("/users")
            @doc(
                summary="List all users",
                description="Returns a paginated list of users",
                tags=["Users"]
            )
            async def list_users(request):
                return JSONResponse([])

    Example:
        With operationId and deprecation::

            @app.get("/old-endpoint")
            @doc(
                summary="Legacy endpoint",
                deprecated=True,
                operationId="getLegacyData",
                tags=["Deprecated"]
            )
            async def legacy_endpoint(request):
                return JSONResponse({"warning": "This endpoint is deprecated"})

    Example:
        With external docs and custom extension::

            @app.post("/users")
            @doc(
                summary="Create user",
                description="Creates a new user account",
                tags=["Users"],
                externalDocs={
                    "description": "User creation guide",
                    "url": "https://docs.example.com/users/create"
                },
                x_custom_field="custom value"
            )
            async def create_user(request):
                return JSONResponse({}, status=201)

    Example:
        Multiple tags and operation-specific servers::

            @app.get("/special")
            @doc(
                summary="Special operation",
                tags=["Special", "Admin"],
                servers=[
                    {"url": "https://special.example.com", "description": "Special server"}
                ]
            )
            async def special_operation(request):
                return JSONResponse({"status": "ok"})

    Note:
        - The operationId field receives special handling and is promoted to the
          top level of the operation metadata for use by the generator.
        - All other fields are stored in the "doc" metadata section.
        - Fields can be overridden by applying the decorator multiple times;
          later applications merge with earlier ones.
        - Markdown is supported in description fields.

    See Also:
        - OpenAPI Operation Object: https://spec.openapis.org/oas/v3.1.0#operation-object
        - @response: Define response specifications
        - @request_body: Define request body schema
        - @param: Add additional parameters
    """
    def decorator(func: Callable):
        meta = _ensure_openapi_meta(func)
        meta_doc = meta.get("doc") or {}
        meta_doc.update(fields)
        meta["doc"] = meta_doc
        # Allow explicit operationId override
        if "operationId" in fields:
            meta["operationId"] = fields["operationId"]
        return func
    return decorator


def response(status: int | str, description: str | None = None, *, model: Any | None = None, media_types: list[str] | None = None, content: dict | None = None, headers: dict | None = None, links: dict | None = None):
    """Define an OpenAPI response specification for a specific status code.

    This decorator adds response documentation for a particular HTTP status code.
    You can apply this decorator multiple times to document different status codes
    (200, 404, 500, etc.) for the same route handler.

    The decorator supports two approaches for defining response schemas:
        1. Type-safe model approach: Provide a Python type (dataclass, TypedDict,
           msgspec.Struct) that will be converted to JSON Schema automatically.
        2. Manual content approach: Provide explicit content dict for full control.

    Args:
        status: HTTP status code as int or string (e.g., 200, "404", "default").
        description: Human-readable description of the response. Required by OpenAPI.
            Defaults to empty string if not provided.
        model: Python type to generate response schema from (dataclass, TypedDict,
            msgspec.Struct, etc.). Mutually exclusive with content parameter.
        media_types: List of media types for the response when using model parameter.
            Defaults to ["application/json"]. Only used when model is provided.
        content: Explicit OpenAPI content dict for full control. Mutually exclusive
            with model parameter. Use as escape hatch for complex scenarios.
        headers: OpenAPI headers dict describing response headers.
            Example: {"X-Rate-Limit": {"schema": {"type": "integer"}}}
        links: OpenAPI links dict for describing relationships between operations.

    Returns:
        Decorator function that attaches response metadata to the handler.

    Example:
        Basic success response with model::

            from dataclasses import dataclass

            @dataclass
            class User:
                id: int
                name: str
                email: str

            @app.get("/users/<int:id>")
            @doc(summary="Get user by ID", tags=["Users"])
            @response(200, description="User found", model=User)
            @response(404, description="User not found")
            async def get_user(request, id: int):
                return JSONResponse({"id": id, "name": "John", "email": "john@example.com"})

    Example:
        Multiple responses with different models::

            @dataclass
            class ErrorResponse:
                error: str
                code: str

            @app.post("/users")
            @doc(summary="Create user", tags=["Users"])
            @response(201, description="User created", model=User)
            @response(400, description="Invalid input", model=ErrorResponse)
            @response(409, description="User already exists", model=ErrorResponse)
            async def create_user(request):
                return JSONResponse({}, status=201)

    Example:
        Response with custom media types::

            @app.get("/report")
            @doc(summary="Get report", tags=["Reports"])
            @response(
                200,
                description="Report generated",
                model=Report,
                media_types=["application/json", "application/xml"]
            )
            async def get_report(request):
                return JSONResponse({})

    Example:
        Response with headers::

            @app.get("/download")
            @doc(summary="Download file", tags=["Files"])
            @response(
                200,
                description="File downloaded",
                headers={
                    "Content-Disposition": {
                        "schema": {"type": "string"},
                        "description": "Attachment filename"
                    },
                    "X-Download-Count": {
                        "schema": {"type": "integer"},
                        "description": "Number of times file was downloaded"
                    }
                }
            )
            async def download_file(request):
                return Response(b"file content", content_type="application/octet-stream")

    Example:
        Manual content specification (escape hatch)::

            @app.get("/complex")
            @doc(summary="Complex response", tags=["Advanced"])
            @response(
                200,
                description="Complex response",
                content={
                    "application/json": {
                        "schema": {
                            "oneOf": [
                                {"$ref": "#/components/schemas/TypeA"},
                                {"$ref": "#/components/schemas/TypeB"}
                            ]
                        }
                    }
                }
            )
            async def complex_endpoint(request):
                return JSONResponse({})

    Example:
        Default response for error handling::

            @app.get("/may-fail")
            @doc(summary="May fail", tags=["Unstable"])
            @response(200, description="Success", model=Data)
            @response("default", description="Unexpected error", model=ErrorResponse)
            async def may_fail(request):
                return JSONResponse({})

    Note:
        - Multiple @response decorators can be stacked for different status codes.
        - If both model and content are provided, model takes precedence.
        - The model parameter triggers automatic JSON Schema generation via type adapters.
        - Empty description defaults to "" but providing descriptive text is recommended.
        - Status code can be "default" to match any undocumented status code.
        - Responses are merged if @response is called multiple times with the same status.

    See Also:
        - OpenAPI Response Object: https://spec.openapis.org/oas/v3.1.0#response-object
        - Type adapters: adapters_dataclasses, adapters_typeddict, adapters_msgspec
        - @doc: General operation metadata
        - @request_body: Define request body schema
    """
    code = str(status)
    def decorator(func: Callable):
        meta = _ensure_openapi_meta(func)
        responses = meta.get("responses") or {}
        resp_obj: dict[str, Any] = {}
        if description is not None:
            resp_obj["description"] = description
        else:
            resp_obj["description"] = ""
        if model is not None:
            resp_obj["__model__"] = model
            if media_types is not None:
                resp_obj["__media_types__"] = media_types
        elif content:
            resp_obj["content"] = content
        if headers:
            resp_obj["headers"] = headers
        if links:
            resp_obj["links"] = links
        # merge
        existing = responses.get(code) or {}
        existing.update(resp_obj)
        responses[code] = existing
        meta["responses"] = responses
        return func
    return decorator


def request_body(*, model: Any | None = None, media_types: list[str] | None = None, description: str | None = None, required: bool | None = None, content: dict | None = None):
    """Define an OpenAPI request body specification for a route handler.

    This decorator documents the expected request body structure for operations
    that accept request bodies (POST, PUT, PATCH, etc.). It supports both
    type-safe model-based schema generation and manual content specification.

    The decorator supports two approaches:
        1. Type-safe model approach: Provide a Python type (dataclass, TypedDict,
           msgspec.Struct) that will be converted to JSON Schema automatically.
        2. Manual content approach: Provide explicit content dict for full control.

    Args:
        model: Python type to generate request body schema from (dataclass,
            TypedDict, msgspec.Struct, etc.). Preferred approach. Mutually
            exclusive with content parameter.
        media_types: List of media types the request body can be in when using
            model parameter. Defaults to ["application/json"]. Common values:
            ["application/json", "application/xml", "multipart/form-data"].
        description: Human-readable description of the request body.
        required: Whether the request body is required. Defaults to None (not
            specified in spec, typically treated as true for these HTTP methods).
        content: Explicit OpenAPI content dict for full control. Mutually exclusive
            with model parameter. Use as escape hatch for complex scenarios.

    Returns:
        Decorator function that attaches request body metadata to the handler.

    Example:
        Basic request body with dataclass::

            from dataclasses import dataclass

            @dataclass
            class CreateUserRequest:
                name: str
                email: str
                age: int

            @app.post("/users")
            @doc(summary="Create user", tags=["Users"])
            @request_body(
                model=CreateUserRequest,
                description="User data to create",
                required=True
            )
            @response(201, description="User created", model=User)
            async def create_user(request):
                data = await request.json()
                return JSONResponse(data, status=201)

    Example:
        Request body with TypedDict::

            from typing import TypedDict

            class UpdateUserRequest(TypedDict):
                name: str | None
                email: str | None

            @app.patch("/users/<int:id>")
            @doc(summary="Update user", tags=["Users"])
            @request_body(
                model=UpdateUserRequest,
                description="Partial user update data"
            )
            @response(200, description="User updated", model=User)
            async def update_user(request, id: int):
                data = await request.json()
                return JSONResponse(data)

    Example:
        Request body with msgspec.Struct::

            import msgspec

            class LoginRequest(msgspec.Struct):
                username: str
                password: str
                remember_me: bool = False

            @app.post("/auth/login")
            @doc(summary="Login", tags=["Auth"])
            @request_body(
                model=LoginRequest,
                description="Login credentials",
                required=True
            )
            @response(200, description="Login successful")
            async def login(request):
                data = await request.json()
                return JSONResponse({"token": "..."})

    Example:
        Multiple media types::

            @app.post("/upload")
            @doc(summary="Upload document", tags=["Documents"])
            @request_body(
                model=Document,
                media_types=["application/json", "application/xml"],
                description="Document in JSON or XML format",
                required=True
            )
            @response(201, description="Document uploaded")
            async def upload_document(request):
                return JSONResponse({}, status=201)

    Example:
        Manual content specification (escape hatch)::

            @app.post("/complex")
            @doc(summary="Complex input", tags=["Advanced"])
            @request_body(
                description="Complex request body",
                required=True,
                content={
                    "application/json": {
                        "schema": {
                            "oneOf": [
                                {"$ref": "#/components/schemas/TypeA"},
                                {"$ref": "#/components/schemas/TypeB"}
                            ]
                        }
                    },
                    "multipart/form-data": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "file": {"type": "string", "format": "binary"}
                            }
                        }
                    }
                }
            )
            async def complex_input(request):
                return JSONResponse({})

    Example:
        Optional request body::

            @app.post("/filter")
            @doc(summary="Filter data", tags=["Data"])
            @request_body(
                model=FilterCriteria,
                description="Optional filter criteria",
                required=False
            )
            @response(200, description="Filtered results")
            async def filter_data(request):
                if request.headers.get("content-length"):
                    data = await request.json()
                else:
                    data = {}
                return JSONResponse([])

    Note:
        - Only one @request_body decorator should be applied per route handler.
        - If both model and content are provided, model takes precedence.
        - The model parameter triggers automatic JSON Schema generation via type adapters.
        - The required parameter is optional; OpenAPI 3.1 defaults vary by HTTP method.
        - For file uploads, use manual content with multipart/form-data media type.

    See Also:
        - OpenAPI Request Body Object: https://spec.openapis.org/oas/v3.1.0#request-body-object
        - Type adapters: adapters_dataclasses, adapters_typeddict, adapters_msgspec
        - @doc: General operation metadata
        - @response: Define response specifications
    """
    def decorator(func: Callable):
        meta = _ensure_openapi_meta(func)
        rb: dict[str, Any] = {}
        if description is not None:
            rb["description"] = description
        if required is not None:
            rb["required"] = required
        if model is not None:
            rb["__model__"] = model
            if media_types is not None:
                rb["__media_types__"] = media_types
        elif content is not None:
            rb["content"] = content
        meta["requestBody"] = rb
        return func
    return decorator


def param(name: str, in_: str = "query", *, required: bool | None = None, description: str | None = None, schema: dict | None = None, **extra):
    """Add an OpenAPI parameter specification to a route handler.

    This decorator documents additional parameters beyond path parameters (which are
    auto-generated from route patterns). Use this for query strings, headers, and
    cookies. Multiple @param decorators can be stacked to document multiple parameters.

    Args:
        name: The name of the parameter. For path parameters, must match the route
            pattern variable name. For headers, use standard header names.
        in_: Where the parameter appears. Valid values:
            - "query": Query string parameter (?key=value)
            - "header": HTTP header parameter
            - "cookie": Cookie parameter
            - "path": Path parameter (usually auto-generated, rarely needed manually)
        required: Whether the parameter is required. Path parameters are always
            required. Query/header/cookie parameters default to optional if not specified.
        description: Human-readable description of the parameter.
        schema: OpenAPI schema object or Python type for the parameter value.
            If a Python type is provided, it will be converted to JSON Schema.
            Example: {"type": "string", "pattern": "^[a-z]+$"}
        **extra: Additional OpenAPI parameter fields like style, explode, example,
            examples, deprecated, allowEmptyValue, etc.

    Returns:
        Decorator function that attaches parameter metadata to the handler.

    Example:
        Query parameters::

            @app.get("/users")
            @doc(summary="List users", tags=["Users"])
            @param("limit", in_="query", description="Maximum results", schema={"type": "integer", "minimum": 1, "maximum": 100})
            @param("offset", in_="query", description="Pagination offset", schema={"type": "integer", "minimum": 0})
            @param("sort", in_="query", description="Sort field", schema={"type": "string", "enum": ["name", "created", "updated"]})
            @response(200, description="User list", model=list[User])
            async def list_users(request):
                limit = int(request.args.get("limit", 10))
                offset = int(request.args.get("offset", 0))
                return JSONResponse([])

    Example:
        Required query parameter::

            @app.get("/search")
            @doc(summary="Search", tags=["Search"])
            @param("q", in_="query", required=True, description="Search query", schema={"type": "string", "minLength": 1})
            @response(200, description="Search results")
            async def search(request):
                query = request.args["q"]
                return JSONResponse([])

    Example:
        Header parameters::

            @app.get("/data")
            @doc(summary="Get data", tags=["Data"])
            @param("X-API-Key", in_="header", required=True, description="API key for authentication", schema={"type": "string"})
            @param("X-Request-ID", in_="header", description="Optional request tracking ID", schema={"type": "string", "format": "uuid"})
            @response(200, description="Data retrieved")
            async def get_data(request):
                api_key = request.headers["X-API-Key"]
                return JSONResponse({})

    Example:
        Cookie parameters::

            @app.get("/profile")
            @doc(summary="Get profile", tags=["Users"])
            @param("session", in_="cookie", required=True, description="Session cookie", schema={"type": "string"})
            @response(200, description="User profile")
            async def get_profile(request):
                session = request.cookies["session"]
                return JSONResponse({})

    Example:
        Parameter with examples::

            @app.get("/items")
            @doc(summary="Get items", tags=["Items"])
            @param(
                "filter",
                in_="query",
                description="Filter expression",
                schema={"type": "string"},
                examples={
                    "simple": {
                        "value": "status:active",
                        "summary": "Filter by active status"
                    },
                    "complex": {
                        "value": "status:active AND category:electronics",
                        "summary": "Multiple filters"
                    }
                }
            )
            @response(200, description="Filtered items")
            async def get_items(request):
                return JSONResponse([])

    Example:
        Parameter with Python type schema::

            @app.get("/calculate")
            @doc(summary="Calculate", tags=["Math"])
            @param("value", in_="query", required=True, description="Input value", schema=int)
            @response(200, description="Calculation result")
            async def calculate(request):
                value = int(request.args["value"])
                return JSONResponse({"result": value * 2})

    Example:
        Deprecated parameter::

            @app.get("/legacy")
            @doc(summary="Legacy endpoint", tags=["Deprecated"])
            @param("old_param", in_="query", description="Use new_param instead", deprecated=True, schema={"type": "string"})
            @param("new_param", in_="query", description="New parameter", schema={"type": "string"})
            @response(200, description="Success")
            async def legacy_endpoint(request):
                return JSONResponse({})

    Note:
        - Path parameters are automatically extracted from route patterns like
          /users/<int:id> and usually don't need @param decoration.
        - Multiple @param decorators can be stacked for multiple parameters.
        - If schema is a Python type (int, str, etc.), it will be converted to
          JSON Schema automatically.
        - The **extra parameter allows any OpenAPI parameter field to be specified.
        - Query/header/cookie parameters default to optional unless required=True.

    See Also:
        - OpenAPI Parameter Object: https://spec.openapis.org/oas/v3.1.0#parameter-object
        - @doc: General operation metadata
        - @response: Define response specifications
        - @request_body: Define request body schema
    """
    def decorator(func: Callable):
        meta = _ensure_openapi_meta(func)
        params = meta.get("parameters") or []
        p: dict[str, Any] = {"name": name, "in": in_}
        if required is not None:
            p["required"] = required
        if description is not None:
            p["description"] = description
        if schema is not None:
            p["schema"] = schema
        if extra:
            p.update(extra)
        params.append(p)
        meta["parameters"] = params
        return func
    return decorator


def security(*requirements: dict):
    """Attach operation-level security requirements to a route handler.

    This decorator specifies which security schemes must be satisfied to access
    an operation. Security schemes must be defined in the global components or
    passed to attach_openapi(). Multiple requirements can be specified, and each
    requirement can include scopes for OAuth2/OpenID Connect.

    Args:
        *requirements: One or more security requirement objects. Each requirement
            is a dict mapping security scheme names to lists of scopes.
            Example: {"bearerAuth": []}, {"oauth2": ["read:users", "write:users"]}
            Multiple requirements mean ANY of them can be satisfied (OR logic).
            Multiple schemes in one requirement means ALL must be satisfied (AND logic).

    Returns:
        Decorator function that attaches security metadata to the handler.

    Example:
        Bearer token authentication::

            # First define the security scheme in attach_openapi()
            attach_openapi(
                app,
                components={
                    "securitySchemes": {
                        "bearerAuth": {
                            "type": "http",
                            "scheme": "bearer",
                            "bearerFormat": "JWT"
                        }
                    }
                }
            )

            @app.get("/protected")
            @doc(summary="Protected endpoint", tags=["Auth"])
            @security({"bearerAuth": []})
            @response(200, description="Success")
            async def protected_endpoint(request):
                return JSONResponse({"data": "secret"})

    Example:
        OAuth2 with scopes::

            attach_openapi(
                app,
                components={
                    "securitySchemes": {
                        "oauth2": {
                            "type": "oauth2",
                            "flows": {
                                "authorizationCode": {
                                    "authorizationUrl": "https://example.com/oauth/authorize",
                                    "tokenUrl": "https://example.com/oauth/token",
                                    "scopes": {
                                        "read:users": "Read user data",
                                        "write:users": "Modify user data",
                                        "admin": "Admin access"
                                    }
                                }
                            }
                        }
                    }
                }
            )

            @app.get("/users")
            @doc(summary="List users", tags=["Users"])
            @security({"oauth2": ["read:users"]})
            @response(200, description="User list")
            async def list_users(request):
                return JSONResponse([])

            @app.delete("/users/<int:id>")
            @doc(summary="Delete user", tags=["Users"])
            @security({"oauth2": ["write:users", "admin"]})
            @response(204, description="User deleted")
            async def delete_user(request, id: int):
                return Response("", status=204)

    Example:
        Multiple authentication methods (OR logic)::

            attach_openapi(
                app,
                components={
                    "securitySchemes": {
                        "bearerAuth": {"type": "http", "scheme": "bearer"},
                        "apiKey": {"type": "apiKey", "in": "header", "name": "X-API-Key"}
                    }
                }
            )

            @app.get("/flexible")
            @doc(summary="Flexible auth", tags=["Auth"])
            @security({"bearerAuth": []}, {"apiKey": []})
            @response(200, description="Success")
            async def flexible_auth(request):
                # Can authenticate with EITHER bearer token OR API key
                return JSONResponse({})

    Example:
        Multiple schemes required simultaneously (AND logic)::

            @app.get("/double-auth")
            @doc(summary="Double authentication required", tags=["Auth"])
            @security({"bearerAuth": [], "apiKey": []})
            @response(200, description="Success")
            async def double_auth(request):
                # Requires BOTH bearer token AND API key
                return JSONResponse({})

    Example:
        API key in header::

            attach_openapi(
                app,
                components={
                    "securitySchemes": {
                        "apiKey": {
                            "type": "apiKey",
                            "in": "header",
                            "name": "X-API-Key"
                        }
                    }
                }
            )

            @app.get("/api/data")
            @doc(summary="Get data", tags=["API"])
            @security({"apiKey": []})
            @response(200, description="Data retrieved")
            async def get_api_data(request):
                return JSONResponse({})

    Example:
        Basic authentication::

            attach_openapi(
                app,
                components={
                    "securitySchemes": {
                        "basicAuth": {
                            "type": "http",
                            "scheme": "basic"
                        }
                    }
                }
            )

            @app.get("/basic")
            @doc(summary="Basic auth endpoint", tags=["Auth"])
            @security({"basicAuth": []})
            @response(200, description="Authenticated")
            async def basic_auth(request):
                return JSONResponse({})

    Note:
        - Security schemes must be defined in components.securitySchemes first.
        - Empty scope list [] is required even when scopes don't apply (e.g., Bearer).
        - Multiple requirements = OR logic (any requirement satisfies access).
        - Multiple schemes in one requirement = AND logic (all must be satisfied).
        - This decorator sets operation-level security, overriding global security.
        - To make an endpoint publicly accessible, don't apply @security decorator.

    See Also:
        - OpenAPI Security Requirement: https://spec.openapis.org/oas/v3.1.0#security-requirement-object
        - OpenAPI Security Scheme: https://spec.openapis.org/oas/v3.1.0#security-scheme-object
        - attach_openapi: Define global security schemes in components parameter
        - @doc: General operation metadata
    """
    def decorator(func: Callable):
        meta = _ensure_openapi_meta(func)
        meta["security"] = list(requirements)
        return func
    return decorator
