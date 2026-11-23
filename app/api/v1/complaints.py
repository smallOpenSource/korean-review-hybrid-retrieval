"""
Complaints API endpoints.
"""

from flask import jsonify, request
from . import api_bp
from app.api.models_extended import ComplaintUpdateRequest
from app.utils.validation import validate_request_body
from app.constants import ResponseStatus, success_response, error_response


@api_bp.route('/complaints', methods=['GET'])
def get_complaints():
    """Get list of complaints with filtering."""
    try:
        from app.services.review_service import get_review_service

        page = int(request.args.get('page', 1))
        size = int(request.args.get('size', 20))
        status = request.args.get('status')
        dept = request.args.get('dept')

        filters = {"complaint.is_complaint": True}
        if status:
            filters["complaint.status"] = status
        if dept:
            filters["complaint.primary_dept"] = dept

        service = get_review_service()
        
        # Build query manually for now as search_similar is for vector search
        # We can reuse the generic search logic from reviews.py or add a method to service
        # For now, let's use service._os.sync_client directly via run_async for flexibility
        
        query = {
            "from": (page - 1) * size,
            "size": size,
            "query": {"bool": {"filter": service._build_filter(filters)}},
            "sort": [{"complaint.urgency": {"order": "desc"}}, {"review_date": {"order": "desc"}}]
        }

        response = service._os.sync_client.search(index=service._index, body=query)
        
        total = response['hits']['total']['value']
        complaints = [hit['_source'] for hit in response['hits']['hits']]

        return jsonify(success_response({
            'complaints': complaints,
            'pagination': {
                'page': page,
                'size': size,
                'total': total,
                'total_pages': (total + size - 1) // size
            }
        }))
    except Exception as e:
        return jsonify(error_response(
            message=str(e),
            error_code='FETCH_COMPLAINTS_ERROR'
        )), 500


@api_bp.route('/complaints/<complaint_id>', methods=['GET'])
def get_complaint(complaint_id: str):
    """Get a single complaint by ID."""
    try:
        from app.services.review_service import get_review_service

        service = get_review_service()
        complaint = service.get_review(complaint_id)

        if not complaint or not complaint.get('complaint', {}).get('is_complaint'):
            return jsonify(error_response(
                message='Complaint not found',
                error_code='COMPLAINT_NOT_FOUND'
            )), 404

        return jsonify(success_response({
            'complaint_id': complaint_id,
            'complaint': complaint
        }))
    except Exception as e:
        return jsonify(error_response(
            message=str(e),
            error_code='FETCH_COMPLAINT_ERROR'
        )), 500


@api_bp.route('/complaints/<complaint_id>', methods=['PATCH'])
@validate_request_body(ComplaintUpdateRequest)
def update_complaint(complaint_id: str, validated_data: ComplaintUpdateRequest):
    """Update complaint status.

    Body validated by ComplaintUpdateRequest:
    - status: ComplaintStatus enum (optional)
    - assigned_to: str (optional, max 100 chars)
    - notes: str (optional, max 1000 chars, whitespace validated)
    """
    try:
        from app.services.review_service import get_review_service

        updates = {}

        if validated_data.status:
            updates['complaint.status'] = validated_data.status.value
        if validated_data.assigned_to:
            updates['complaint.assigned_to'] = validated_data.assigned_to
        if validated_data.notes:
            updates['complaint.notes'] = validated_data.notes

        if not updates:
            return jsonify(error_response(
                message='No updates provided',
                error_code='NO_UPDATES'
            )), 400

        service = get_review_service()
        success = service.update_review(complaint_id, updates)

        if not success:
            return jsonify(error_response(
                message='Failed to update complaint',
                error_code='UPDATE_FAILED'
            )), 500

        return jsonify(success_response({
            'complaint_id': complaint_id,
            'updated': True
        }))
    except Exception as e:
        return jsonify(error_response(
            message=str(e),
            error_code='UPDATE_COMPLAINT_ERROR'
        )), 500


@api_bp.route('/complaints/<complaint_id>/escalate', methods=['POST'])
def escalate_complaint(complaint_id: str):
    """Escalate a complaint."""
    try:
        from app.services.review_service import get_review_service

        service = get_review_service()
        updates = {
            'complaint.escalation_required': True,
            'complaint.escalation_level': 'manager',
            'complaint.status': 'escalated'
        }
        
        success = service.update_review(complaint_id, updates)

        if not success:
            return jsonify(error_response(
                message='Failed to escalate complaint',
                error_code='ESCALATION_FAILED'
            )), 500

        return jsonify(success_response({
            'complaint_id': complaint_id,
            'escalated': True
        }))
    except Exception as e:
        return jsonify(error_response(
            message=str(e),
            error_code='ESCALATE_COMPLAINT_ERROR'
        )), 500
