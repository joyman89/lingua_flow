import logging
import subprocess
import time
from flask import Flask, request, send_file, jsonify, after_this_request
from PyPDF2 import PdfReader
from PyPDF2.errors import PdfReadError
from deep_translator import GoogleTranslator
from gtts import gTTS
import speech_recognition as sr
from pydub import AudioSegment
import tempfile
import os

# Configure logging
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# Constants
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_TEXT_LENGTH = 5000  # Max chars for translation/TTS
VALID_STT_LANGS = ['en-US', 'fr-FR', 'es-ES', 'de-DE', 'my-MM']  # Supported STT languages

# HTML content (updated with audio-to-audio mode)
INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>PDF & Audio Translator</title>
  <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap" rel="stylesheet" />
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet" />
  <style>
    body {
      background: linear-gradient(135deg, #0F172A, #1E293B);
      height: 100vh;
      margin: 0;
      padding: 0;
      font-family: 'Roboto', sans-serif;
      overflow-x: hidden;
      display: flex;
      flex-direction: column;
      justify-content: center;
      position: relative;
    }
    body::before {
      content: '';
      position: absolute;
      width: 100%;
      height: 100%;
      background: radial-gradient(circle, rgba(107, 70, 193, 0.1) 0%, transparent 70%);
      animation: pulse 10s infinite;
      z-index: -1;
    }
    @keyframes pulse {
      0% { transform: scale(1); }
      50% { transform: scale(1.2); }
      100% { transform: scale(1); }
    }
    .container {
      max-width: 600px;
      width: 100%;
      padding: 20px;
      flex: 1;
      z-index: 1;
    }
    .header {
      text-align: center;
      margin-bottom: 40px;
      padding: 20px;
      background: linear-gradient(90deg, #2D2D44, #3A3A5A);
      border-radius: 15px;
      box-shadow: 0 6px 20px rgba(0, 0, 0, 0.4);
      transform: perspective(500px) rotateX(5deg);
      transition: transform 0.3s;
    }
    .header:hover {
      transform: perspective(500px) rotateX(0deg) scale(1.02);
    }
    .header img {
      max-width: 200px;
      height: auto;
      background: linear-gradient(90deg, #6B46C1, #4C51BF);
      padding: 10px;
      border-radius: 10px;
      box-shadow: 0 4px 15px rgba(107, 70, 193, 0.3);
      transition: transform 0.3s;
    }
    .header img:hover {
      transform: scale(1.1);
    }
    .card {
      background: linear-gradient(135deg, #2D2D44, #3A3A5A);
      border-radius: 20px;
      padding: 35px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5), 0 0 20px rgba(107, 70, 193, 0.2);
      border: 1px solid #5A5A7A;
      position: relative;
      overflow: hidden;
      transform-style: preserve-3d;
    }
    .card::before {
      content: '';
      position: absolute;
      top: -50%;
      left: -50%;
      width: 200%;
      height: 200%;
      background: radial-gradient(circle, rgba(107, 70, 193, 0.1) 0%, transparent 70%);
      animation: rotate 20s linear infinite;
      z-index: -1;
    }
    @keyframes rotate {
      0% { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }
    .intro {
      text-align: center;
      color: #A5C9FF;
      margin-bottom: 30px;
      font-size: 1rem;
      text-shadow: 0 0 10px rgba(165, 201, 255, 0.3), 0 0 20px rgba(107, 70, 193, 0.2);
      padding: 15px;
      background: rgba(45, 45, 70, 0.9);
      border-radius: 10px;
    }
    .form-group {
      margin-bottom: 25px;
    }
    .form-label {
      font-weight: 700;
      color: #E6ECEF;
      font-size: 1.1rem;
      margin-bottom: 10px;
      text-shadow: 0 0 5px rgba(230, 236, 239, 0.3);
    }
    .form-control {
      background: linear-gradient(135deg, #3D3D5A, #4A4A70);
      border: 2px solid #6B7280;
      color: #F9FAFB;
      border-radius: 10px;
      padding: 12px 15px;
      font-size: 1rem;
      width: 100%;
      transition: all 0.3s ease;
      position: relative;
    }
    .form-control:focus {
      border-color: #A855F7;
      box-shadow: 0 0 15px rgba(168, 85, 247, 0.5), inset 0 0 10px rgba(168, 85, 247, 0.2);
      transform: scale(1.02);
    }
    .form-control::before {
      content: '';
      position: absolute;
      top: -2px;
      left: -2px;
      right: -2px;
      bottom: -2px;
      background: linear-gradient(45deg, #6B46C1, #4C51BF);
      z-index: -1;
      border-radius: 12px;
      opacity: 0;
      transition: opacity 0.3s;
    }
    .form-control:focus::before {
      opacity: 0.1;
    }
    .btn-primary {
      background: linear-gradient(90deg, #6B46C1, #4C51BF);
      border: none;
      padding: 14px;
      font-weight: 700;
      border-radius: 10px;
      width: 100;
      font-size: 1.2rem;
      text-shadow: 0 0 5px rgba(255, 255, 255, 0.3);
      position: relative;
      overflow: hidden;
      transition: all 0.3s ease;
    }
    .btn-primary::after {
      content: '';
      position: absolute;
      top: 50%;
      left: 50%;
      width: 0;
      height: 0;
      background: rgba(255, 255, 255, 0.2);
      border-radius: 50%;
      transform: translate(-50%, -50%);
      transition: width 0.6s, height 0.6s;
      z-index: 0;
    }
    .btn-primary:hover::after {
      width: 300%;
      height: 300%;
    }
    .btn-primary:hover {
      transform: scale(1.05);
      background: linear-gradient(90deg, #7C3AED, #5B21B6);
      box-shadow: 0 0 20px rgba(124, 58, 237, 0.5);
    }
    .progress {
      height: 12px;
      background: #3D3D5A;
      border-radius: 6px;
      margin-top: 20px;
      box-shadow: inset 0 0 5px rgba(0, 0, 0, 0.3);
      overflow: hidden;
    }
    .progress-bar {
      background: linear-gradient(90deg, #6B46C1, #4C51BF);
      box-shadow: 0 0 10px rgba(107, 70, 193, 0.3);
      border-right: 3px solid #A5B4FC55;
    }
    .output {
      margin-top: 30px;
      color: #E6ECEF;
      text-shadow: 0 0 5px rgba(230, 236, 239, 0.3);
    }
    #player, #outputText {
      width: 100%;
      background: linear-gradient(135deg, #3D3D5A, #4A4A70);
      border: 2px solid #6B7280;
      border-radius: 10px;
      padding: 15px;
      box-shadow: 0 0 10px rgba(0, 0, 0, 0.2);
    }
    #outputText {
      resize: vertical;
      min-height: 150px;
    }
    .hidden {
      display: none;
    }
    .features {
      margin-top: 30px;
      font-size: 0.95rem;
      color: #A5C9FF;
      text-shadow: 0 0 5px rgba(165, 201, 255, 0.3);
    }
    .feature-item {
      margin-bottom: 15px;
      padding-left: 15px;
      border-left: 4px solid #6B46C1;
      background: rgba(45, 45, 70, 0.9);
      padding: 10px;
      border-radius: 5px;
      transition: transform 0.3s;
    }
    .feature-item:hover {
      transform: translateX(10px);
    }
    .footer {
      text-align: center;
      padding: 20px;
      color: #A0AEC0;
      font-size: 0.9rem;
      background: linear-gradient(90deg, #2D2D44, #3A3A5A);
      border-top: 1px solid #5A5A7A;
      margin-top: auto;
      animation: fadeIn 2s ease-in-out;
    }
    @keyframes fadeIn {
      0% { opacity: 0; }
      100% { opacity: 1; }
    }
    @media (max-width: 576px) {
      .container { padding: 10px; }
      .card { padding: 20px; }
      .header img { max-width: 150px; }
      .intro { font-size: 0.9rem; }
      .footer { font-size: 0.8rem; }
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <img src="https://via.placeholder.com/200x70?text=PDF+AI" alt="PDF AI Logo" />
    </div>
    <div class="intro">
      Transform your documents and audio with AI-powered processing. Extract, translate, and convert between text and speech with ease.<br>
      <strong>Fast Processing | AI Powered | 20+ Languages</strong>
    </div>
    <div class="card">
      <form id="toolForm" enctype="multipart/form-data">
        <div class="form-group">
          <label class="form-label">Choose Your Processing Mode</label>
          <select class="form-control" id="mode" name="mode">
            <option value="pdf_audio">PDF → Audio<br>Convert PDF text to speech</option>
            <option value="pdf_translate">PDF → Translate<br>Extract and translate PDF text</option>
            <option value="pdf_translate_audio">PDF → Translate → Audio<br>Translate PDF then convert to speech</option>
            <option value="audio_text">Audio → Text<br>Convert speech to text</option>
            <option value="audio_translate">Audio → Translate<br>Convert speech to text and translate</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">Target Language</label>
          <select class="form-control" id="lang" name="lang">
            <option value="en">English</option>
            <option value="my">Myanmar</option>
            <option value="fr">French</option>
            <option value="es">Spanish</option>
            <option value="de">German</option>
          </select>
        </div>
        <div class="form-group" id="pdfInput">
          <label class="form-label">1. Upload File</label>
          <input type="file" class="form-control" id="pdf" name="pdf" accept="application/pdf" />
          <div>No file chosen</div>
        </div>
        <div class="form-group hidden" id="audioInput">
          <label class="form-label">1. Upload File</label>
          <input type="file" class="form-control" id="audio" name="audio" accept="audio/*" />
          <div>Drag & drop your audio file here, or click to browse<br>Supported: MP3, WAV, M4A, OGG</div>
        </div>
        <div class="form-group hidden" id="sttLangRow">
          <label class="form-label">Speech Language</label>
          <input type="text" class="form-control" id="stt_lang" name="stt_lang" placeholder="en-US (e.g., en-US, fr-FR)" value="en-US" />
        </div>
        <button type="submit" class="btn btn-primary">2. Process<br>Start Processing<br>Please upload a file first</button>
        <div class="progress hidden" id="progressWrap">
          <div class="progress-bar progress-bar-striped progress-bar-animated" style="width:100%"></div>
        </div>
      </form>
      <div class="output">
        <div>Results</div>
        <audio id="player" class="hidden" controls></audio>
        <textarea id="outputText" class="form-control hidden" placeholder="Results will appear here<br>Upload a file and start processing to see results"></textarea>
      </div>
      <div class="features">
        <div class="feature-item"><strong>Powerful AI Processing Features</strong></div>
        <div class="feature-item">PDF Text Extraction<br>Extract text from any PDF document with OCR support</div>
        <div class="feature-item">Multi-Language Translation<br>Translate between 20+ languages instantly</div>
        <div class="feature-item">Text-to-Speech<br>Convert text to natural-sounding audio</div>
        <div class="feature-item">Speech Recognition<br>Convert audio to accurate text transcription</div>
      </div>
    </div>
    <div class="footer">
      © A&T Group Strategy First AI Hackathon 2025
    </div>
  </div>

  <script>
    const modeSel = document.getElementById('mode');
    const pdfInput = document.getElementById('pdfInput');
    const audioInput = document.getElementById('audioInput');
    const sttLangRow = document.getElementById('sttLangRow');
    const progressWrap = document.getElementById('progressWrap');
    const player = document.getElementById('player');
    const outputText = document.getElementById('outputText');
    const pdfFileInput = document.getElementById('pdf');
    const audioFileInput = document.getElementById('audio');

    function updateFormVisibility() {
      const m = modeSel.value;
      const pdfNeeded = (m === 'pdf_audio' || m === 'pdf_translate' || m === 'pdf_translate_audio');
      pdfInput.classList.toggle('hidden', !pdfNeeded);
      audioInput.classList.toggle('hidden', pdfNeeded);
      sttLangRow.classList.toggle('hidden', !(m === 'audio_text' || m === 'audio_translate'));
      updateFileStatus();
    }

    function updateFileStatus() {
      const pdfFile = pdfFileInput.files[0];
      const audioFile = audioFileInput.files[0];
      if (pdfFile) pdfInput.querySelector('div').textContent = pdfFile.name;
      if (audioFile) audioInput.querySelector('div').textContent = audioFile.name;
    }

    modeSel.addEventListener('change', updateFormVisibility);
    pdfFileInput.addEventListener('change', updateFileStatus);
    audioFileInput.addEventListener('change', updateFileStatus);
    updateFormVisibility();

    document.getElementById('toolForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      progressWrap.classList.remove('hidden');
      player.classList.add('hidden');
      outputText.classList.add('hidden');
      outputText.value = '';

      const m = modeSel.value;
      const lang = document.getElementById('lang').value;
      const sttLang = document.getElementById('stt_lang').value;
      const maxFileSize = 10 * 1024 * 1024; // 10MB

      const fd = new FormData();
      if (m.startsWith('pdf')) {
        const pdf = document.getElementById('pdf').files[0];
        if (!pdf) { alert('Please choose a document.'); progressWrap.classList.add('hidden'); return; }
        if (pdf.size > maxFileSize) { alert('Document file is too large (max 10MB).'); progressWrap.classList.add('hidden'); return; }
        fd.append('pdf', pdf);
        fd.append('lang', lang);
      } else {
        const audio = document.getElementById('audio').files[0];
        if (!audio) { alert('Please choose an audio file.'); progressWrap.classList.add('hidden'); return; }
        if (audio.size > maxFileSize) { alert('Audio file is too large (max 10MB).'); progressWrap.classList.add('hidden'); return; }
        fd.append('audio', audio);
        fd.append('lang', lang);
        fd.append('stt_lang', sttLang);
      }

      const endpoints = {
        pdf_audio: '/pdf-to-audio',
        pdf_translate: '/pdf-to-translate',
        pdf_translate_audio: '/pdf-to-translate-audio',
        audio_text: '/audio-to-text',
        audio_translate: '/audio-to-translate',
        audio_audio: '/audio-to-audio'
      };

      try {
        const res = await fetch(endpoints[m], { method: 'POST', body: fd });
        if (!res.ok) {
          const msg = await res.text();
          alert(`Error: ${msg}`);
          progressWrap.classList.add('hidden');
          return;
        }

        if (m === 'pdf_audio' || m === 'pdf_translate_audio' || m === 'audio_audio') {
          const blob = await res.blob();
          const url = URL.createObjectURL(blob);
          player.src = url;
          player.classList.remove('hidden');
        } else {
          const data = await res.json();
          const text = data.translated_text || data.text || JSON.stringify(data);
          outputText.value = text;
          outputText.classList.remove('hidden');
        }
      } catch (e) {
        alert(`Network error: ${e.message}`);
      }

      progressWrap.classList.add('hidden');
    });
  </script>
</body>
</html>
"""

# ---------------- Helpers ----------------
def check_file_size(file):
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > MAX_FILE_SIZE:
        raise ValueError(f"File size exceeds {MAX_FILE_SIZE / 1024 / 1024}MB limit")
    return file

def limit_text(text: str) -> str:
    if len(text) > MAX_TEXT_LENGTH:
        return text[:MAX_TEXT_LENGTH]
    return text

def validate_stt_lang(lang: str) -> str:
    if lang not in VALID_STT_LANGS:
        raise ValueError(f"Invalid STT language code: {lang}")
    return lang

def extract_text_from_pdf(file_storage) -> str:
    try:
        check_file_size(file_storage)
        reader = PdfReader(file_storage)
    except PdfReadError:
        raise ValueError("Invalid or corrupted PDF file. Please try another file.")

    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            raise ValueError("This PDF is password protected and cannot be processed.")

    text = []
    for page in reader.pages:
        extracted = page.extract_text()
        if extracted:
            text.append(extracted)
    result = "\n".join(text).strip()
    if not result:
        raise ValueError("No readable text found in the PDF.")
    return limit_text(result)

def tts_to_tempfile(text: str, lang: str) -> str:
    text = limit_text(text)
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    tf.close()
    gTTS(text=text, lang=lang).save(tf.name)
    return tf.name

def ensure_wav(input_path: str) -> str:
    audio = AudioSegment.from_file(input_path)
    wav_path = tempfile.NamedTemporaryFile(delete=False, suffix='.wav').name
    audio.set_channels(1).set_frame_rate(16000).export(wav_path, format='wav')
    return wav_path

def convert_to_wav(audio_file) -> str:
    tf = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
    try:
        # Use pydub to convert the uploaded file to wav
        audio = AudioSegment.from_file(audio_file)
        audio = audio.set_channels(1).set_frame_rate(16000)
        audio.export(tf.name, format='wav')
    except Exception as e:
        raise ValueError(f"Audio conversion failed: {str(e)}")
    return tf.name

def stt_google(audio_path: str, language: str = 'en-US') -> str:
    language = validate_stt_lang(language)
    recognizer = sr.Recognizer()
    wav_path = ensure_wav(audio_path)
    try:
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
        return recognizer.recognize_google(audio_data, language=language)
    except sr.UnknownValueError:
        raise ValueError("Could not understand the audio.")
    except sr.RequestError as e:
        raise ValueError(f"Speech service error: {e}")
    finally:
        try:
            os.unlink(wav_path)
        except Exception as e:
            logging.error(f"Failed to delete temp file {wav_path}: {e}")

# ---------- Routes ----------
@app.route('/')
def index():
    return INDEX_HTML

@app.route('/pdf-to-audio', methods=['POST'])
def pdf_to_audio():
    try:
        pdf = request.files.get('pdf')
        lang = request.form.get('lang', 'en')
        if not pdf:
            return "No PDF uploaded", 400
        text = extract_text_from_pdf(pdf)
        mp3_path = tts_to_tempfile(text, lang)

        @after_this_request
        def cleanup(response):
            try:
                os.remove(mp3_path)
            except Exception as e:
                logging.error(f"Failed to delete temp file {mp3_path}: {e}")
            return response

        return send_file(mp3_path, mimetype='audio/mpeg', as_attachment=True, download_name='audiobook.mp3')
    except Exception as e:
        return str(e), 400

@app.route('/pdf-to-translate', methods=['POST'])
def pdf_to_translate():
    try:
        pdf = request.files.get('pdf')
        target = request.form.get('lang', 'en')
        if not pdf:
            return "No PDF uploaded", 400
        text = extract_text_from_pdf(pdf)
        translated = GoogleTranslator(source='auto', target=target).translate(text)
        return jsonify({"translated_text": translated})
    except Exception as e:
        return str(e), 400

@app.route('/pdf-to-translate-audio', methods=['POST'])
def pdf_to_translate_audio():
    try:
        pdf = request.files.get('pdf')
        target = request.form.get('lang', 'en')
        if not pdf:
            return "No PDF uploaded", 400
        text = extract_text_from_pdf(pdf)
        translated = GoogleTranslator(source='auto', target=target).translate(text)
        mp3_path = tts_to_tempfile(translated, target)

        @after_this_request
        def cleanup(response):
            try:
                os.remove(mp3_path)
            except Exception as e:
                logging.error(f"Failed to delete temp file {mp3_path}: {e}")
            return response

        return send_file(mp3_path, mimetype='audio/mpeg', as_attachment=True, download_name='translated_audiobook.mp3')
    except Exception as e:
        return str(e), 400

@app.route('/audio-to-text', methods=['POST'])
def audio_to_text():
    try:
        audio = request.files.get('audio')
        stt_lang = request.form.get('stt_lang', 'en-US')
        if not audio:
            return "No audio uploaded", 400
        check_file_size(audio)
        wav_path = convert_to_wav(audio)
        text = stt_google(wav_path, language=stt_lang)
        os.remove(wav_path)  # Clean up
        return jsonify({"text": text})
    except Exception as e:
        return str(e), 400

@app.route('/audio-to-translate', methods=['POST'])
def audio_to_translate():
    try:
        audio = request.files.get('audio')
        stt_lang = request.form.get('stt_lang', 'en-US')
        target = request.form.get('lang', 'en')
        if not audio:
            return "No audio uploaded", 400
        check_file_size(audio)
        wav_path = convert_to_wav(audio)
        text = stt_google(wav_path, language=stt_lang)
        os.remove(wav_path)  # Clean up
        translated = GoogleTranslator(source='auto', target=target).translate(text)
        return jsonify({"text": text, "translated_text": translated})
    except Exception as e:
        return str(e), 400

@app.route('/audio-to-audio', methods=['POST'])
def audio_to_audio():
    try:
        audio = request.files.get('audio')
        stt_lang = request.form.get('stt_lang', 'en-US')
        target_lang = request.form.get('lang', 'en')
        if not audio:
            return "No audio uploaded", 400
        check_file_size(audio)
        wav_path = convert_to_wav(audio)
        text = stt_google(wav_path, language=stt_lang)
        os.remove(wav_path)  # Clean up
        mp3_path = tts_to_tempfile(text, target_lang)

        @after_this_request
        def cleanup(response):
            try:
                os.remove(mp3_path)
            except Exception as e:
                logging.error(f"Failed to delete temp file {mp3_path}: {e}")
            return response

        return send_file(mp3_path, mimetype='audio/mpeg', as_attachment=True, download_name='translated_audio.mp3')
    except Exception as e:
        return str(e), 400

if __name__ == '__main__':
    # Run Flask app (Render sets PORT via env var)
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)