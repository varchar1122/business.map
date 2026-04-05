from flask import Flask, render_template, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
from ddgs import DDGS
import requests
from yandex_gpt_api import gpt
from dotenv import load_dotenv
import json
from ai import *  # содержит get_query

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///surveys.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key-here-change-in-production-2024'
db = SQLAlchemy(app)

# Модель данных для анкет
class BusinessSurvey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    survey_id = db.Column(db.String(100), unique=True, nullable=False)
    company_name = db.Column(db.String(200), nullable=False)
    business_type = db.Column(db.String(200), nullable=False)
    region = db.Column(db.String(200), nullable=False)
    website = db.Column(db.String(500), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    submitted_at_ru = db.Column(db.String(100))
    status = db.Column(db.String(50), default='pending')
    
    def to_dict(self):
        return {
            'id': self.id,
            'survey_id': self.survey_id,
            'company_name': self.company_name,
            'business_type': self.business_type,
            'region': self.region,
            'website': self.website,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'submitted_at_ru': self.submitted_at_ru,
            'status': self.status
        }

# Создание таблиц
with app.app_context():
    db.create_all()

# Функция валидации
def validate_survey_data(data):
    errors = {}
    
    company_name = data.get('companyName', '').strip()
    if not company_name:
        errors['companyName'] = 'Введите название бизнеса'
    elif len(company_name) < 2:
        errors['companyName'] = 'Название должно содержать минимум 2 символа'
    
    business_type = data.get('businessType', '').strip()
    if not business_type:
        errors['businessType'] = 'Укажите сферу бизнеса'
    elif len(business_type) < 2:
        errors['businessType'] = 'Сфера бизнеса должна содержать минимум 2 символа'
    
    region = data.get('region', '').strip()
    if not region:
        errors['region'] = 'Укажите город, область или страну'
    elif len(region) < 2:
        errors['region'] = 'Поле должно содержать минимум два символа'
    
    website = data.get('website', '').strip()
    if website and not website.startswith(('http://', 'https://')):
        website = 'https://' + website
    
    return errors, {
        'companyName': company_name,
        'businessType': business_type,
        'region': region,
        'website': website if website else None
    }

# Главная страница
@app.route('/')
def index():
    return render_template('index.html')

# Обработка отправки анкеты
@app.route('/api/submit-survey', methods=['POST'])
def submit_survey():
    try:
        data = request.get_json()
        
        # Валидация данных
        errors, validated_data = validate_survey_data(data)
        
        if errors:
            return jsonify({
                'success': False,
                'errors': errors
            }), 400
        
        # Сохраняем в базу данных
        survey_id = f"SURVEY_{int(datetime.utcnow().timestamp())}"
        submitted_at_ru = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        
        new_survey = BusinessSurvey(
            survey_id=survey_id,
            company_name=validated_data['companyName'],
            business_type=validated_data['businessType'],
            region=validated_data['region'],
            website=validated_data['website'],
            submitted_at_ru=submitted_at_ru,
            status='pending'
        )
        
        db.session.add(new_survey)
        db.session.commit()
        
        # Сохраняем в сессию
        user_survey_result = {
            'companyName': validated_data['companyName'],
            'businessType': validated_data['businessType'],
            'region': validated_data['region'],
            'website': validated_data['website'] if validated_data['website'] else None
        }
        session['last_survey'] = user_survey_result
        
        # Генерация отчёта через нейросеть
        report_text = ""
        try:
            report_text = get_query(user_survey_result)
        except Exception as e:
            report_text = f"Ошибка при генерации отчёта: {str(e)}"
        
        # Формируем ответ (без редиректа)
        response_data = {
            'success': True,
            'survey_id': survey_id,
            'data': user_survey_result,
            'report': report_text   # <-- возвращаем отчёт на фронт
        }
        
        return jsonify(response_data), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Получение последней анкеты из сессии
@app.route('/api/get-last-survey', methods=['GET'])
def get_last_survey():
    last_survey = session.get('last_survey')
    if last_survey:
        return jsonify(last_survey)
    return jsonify({'error': 'No survey found'}), 404

# Получение всех анкет из БД
@app.route('/api/surveys', methods=['GET'])
def get_all_surveys():
    surveys = BusinessSurvey.query.all()
    return jsonify([s.to_dict() for s in surveys])

if __name__ == '__main__':
    app.run(debug=True, port=5000)