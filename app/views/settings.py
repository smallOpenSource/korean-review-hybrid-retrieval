from flask import Blueprint, render_template, request, jsonify
from app.services.settings_service import get_settings_service

bp = Blueprint('settings', __name__)

@bp.route('/settings')
def index():
    service = get_settings_service()
    settings = service.get_all_settings()
    return render_template('pages/settings.html', config=settings)

@bp.route('/api/v1/settings/update', methods=['POST'])
def update_settings():
    try:
        data = request.json
        service = get_settings_service()
        
        # Convert boolean to string for DB storage
        if 'auto_collect' in data:
            data['auto_collect'] = str(data['auto_collect']).lower()
            
        success = service.update_settings(data)
        
        if success:
            return jsonify({'status': 'ok', 'message': '설정이 저장되었습니다.'})
        else:
            return jsonify({'status': 'error', 'message': '설정 저장에 실패했습니다.'}), 500
            
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
