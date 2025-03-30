from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import spacy
from sentence_transformers import SentenceTransformer
import PyPDF2
import docx
import re
import os

app = Flask(__name__)
CORS(app)

# Configuration
app.config.from_object('config.DevelopmentConfig')
db = SQLAlchemy(app)

# Load ML models
nlp = spacy.load("en_core_web_sm")
model = SentenceTransformer('all-MiniLM-L6-v2')  # Lightweight model

class Resume(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(120))
    content = db.Column(db.Text)
    skills = db.Column(db.JSON)
    experience = db.Column(db.String(50))
    score = db.Column(db.Float)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

def parse_resume(file):
    try:
        if file.filename.endswith('.pdf'):
            pdf = PyPDF2.PdfReader(file)
            text = ' '.join([page.extract_text() for page in pdf.pages])
        elif file.filename.endswith('.docx'):
            doc = docx.Document(file)
            text = ' '.join([p.text for p in doc.paragraphs])
        else:
            text = file.read().decode('utf-8')
            
        doc = nlp(text)
        return {
            'skills': [ent.text for ent in doc.ents if ent.label_ == 'SKILL'],
            'experience': re.findall(r'\b(\d+\+? years?)\b', text),
            'text': text
        }
    except Exception as e:
        raise ValueError(f"Error parsing file: {str(e)}")

@app.route('/api/analyze', methods=['POST'])
def analyze_resume():
    if 'resume' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
        
    file = request.files['resume']
    job_desc = request.form.get('job_desc', '')
    
    try:
        # Parse resume
        parsed = parse_resume(file)
        
        # Calculate similarity
        embeddings = model.encode([job_desc, parsed['text']])
        score = (embeddings[0] @ embeddings[1]) / (np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[1]))
        
        # Save to DB
        resume = Resume(
            filename=file.filename,
            content=parsed['text'],
            skills=parsed['skills'],
            experience=', '.join(parsed['experience']),
            score=round(score * 100, 1)
        )
        db.session.add(resume)
        db.session.commit()
        
        return jsonify({
            'score': resume.score,
            'skills': resume.skills,
            'experience': resume.experience
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000)s