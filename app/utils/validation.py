"""
Pydantic validation decorators for Flask endpoints

Provides automatic query parameter and request body validation
with standardized error responses.

Created: 2025-12-31 (Session 2: Input Validation Infrastructure)
"""

from functools import wraps
from flask import request, jsonify
from pydantic import BaseModel, ValidationError
from typing import Type


def validate_query_params(model: Type[BaseModel]):
    """쿼리 파라미터 검증 데코레이터

    Args:
        model: Pydantic BaseModel 클래스

    Usage:
        @validate_query_params(ReviewQueryParams)
        def get_reviews(validated_params: ReviewQueryParams):
            page = validated_params.page
            ...
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                # request.args를 dict로 변환
                params = request.args.to_dict()

                # Pydantic 검증 (자동 타입 변환 포함)
                validated = model(**params)

                # kwargs에 validated_params 추가
                kwargs['validated_params'] = validated
                return fn(*args, **kwargs)

            except ValidationError as e:
                return jsonify({
                    'status': 'error',
                    'error_code': 'VALIDATION_ERROR',
                    'message': 'Invalid query parameters',
                    'details': e.errors()
                }), 400

        return wrapper
    return decorator


def validate_request_body(model: Type[BaseModel]):
    """Request Body 검증 데코레이터

    Args:
        model: Pydantic BaseModel 클래스

    Usage:
        @validate_request_body(AnalyzeRequest)
        def analyze_review(validated_data: AnalyzeRequest):
            content = validated_data.content
            ...
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                data = request.get_json()

                if data is None:
                    return jsonify({
                        'status': 'error',
                        'error_code': 'INVALID_JSON',
                        'message': 'Request body must be valid JSON'
                    }), 400

                # Pydantic 검증
                validated = model(**data)
                kwargs['validated_data'] = validated
                return fn(*args, **kwargs)

            except ValidationError as e:
                return jsonify({
                    'status': 'error',
                    'error_code': 'VALIDATION_ERROR',
                    'message': 'Invalid request body',
                    'details': e.errors()
                }), 400
            except Exception as e:
                return jsonify({
                    'status': 'error',
                    'error_code': 'INVALID_REQUEST',
                    'message': str(e)
                }), 400

        return wrapper
    return decorator
