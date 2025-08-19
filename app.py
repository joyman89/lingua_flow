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

# HTML content (unchanged)
INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>PDF ↔ Audio Translator</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet" />
  <style>
    body{background:linear-gradient(135deg,#6dd5ed,#2193b0);min-height:100vh;display:flex;align-items:center;justify-content:center}
    .card{max-width:760px;width:100%;border-radius:18px;box-shadow:0 10px 30px rgba(0,0,0,.2)}
    .hidden{display:none}
  </style>
</head>
<body>
  <div class="card p-4">
    <h3 class="text-center mb-3">📚 PDF ↔ Audio Translator</h3>
    <p class="text-center text-muted">Five modes: PDF→Audio, PDF→Translate, PDF→Translate→Audio, Audio→Text, Audio→Translate</p>

    <form id="toolForm">
      <div class="row g-3">
        <div class="col-md-6">
          <label class="form-label">Mode</label>
          <select class="form-select" id="mode" name="mode">
            <option value="pdf_audio">PDF → Audio</option>
            <option value="pdf_translate">PDF → Translate (text)</option>
            <option value="pdf_translate_audio">PDF → Translate → Audio</option>
            <option value="audio_text">Audio → Text</option>
            <option value="audio_translate">Audio → Translate Text</option>
          </select>
        </div>
        <div class="col-md-6">
          <label class="form-label">Target Language (for translate / TTS)</label>
          <select class="form-select" id="lang" name="lang">
            <option value="en">English (en)</option>
            <option value="my">Myanmar (my)</option>
            <option value="fr">French (fr)</option>
            <option value="es">Spanish (es)</option>
            <option value="de">German (de)</option>
          </select>
        </div>
      </div>

      <div class="row g-3 mt-1">
        <div class="col-md-6" id="pdfInput">
          <label class="form-label">PDF File</label>
          <input type="file" class="form-control" id="pdf" name="pdf" accept="application/pdf" />
        </div>
        <div class="col-md-6 hidden" id="audioInput">
          <label class="form-label">Audio File (wav/mp3/m4a)</label>
          <input type="file" class="form-control" id="audio" name="audio" accept="audio/*" />
        </div>
      </div>

      <div class="row g-3 mt-1 hidden" id="sttLangRow">
        <div class="col-md-6">
          <label class="form-label">Speech Language (for STT)</label>
          <input type="text" class="form-control" id="stt_lang" name="stt_lang" placeholder="en-US (e.g., en-US, fr-FR, es-ES)" value="en-US" />
        </div>
      </div>

      <button class="btn btn-primary w-100 mt-3" type="submit">Run</button>

      <div class="progress mt-3 hidden" id="progressWrap">
        <div class="progress-bar progress-bar-striped progress-bar-animated" style="width:100%">Processing…</div>
      </div>
    </form>

    <div class="mt-3">
      <audio id="player" class="w-100 hidden" controls></audio>
      <textarea id="outputText" class="form-control hidden" rows="10" placeholder="Result text will appear here..."></textarea>
    </div>
  </div>

  <script>
    const modeSel = document.getElementById('mode');
    const pdfInput = document.getElementById('pdfInput');
    const audioInput = document.getElementById('audioInput');
    const sttLangRow = document.getElementById('sttLangRow');

    function updateFormVisibility(){
      const m = modeSel.value;
      const pdfNeeded = (m === 'pdf_audio' || m === 'pdf_translate' || m === 'pdf_translate_audio');
      pdfInput.classList.toggle('hidden', !pdfNeeded);
      audioInput.classList.toggle('hidden', pdfNeeded);
      sttLangRow.classList.toggle('hidden', !(m === 'audio_text' || m === 'audio_translate'));
    }
    modeSel.addEventListener('change', updateFormVisibility);
    updateFormVisibility();

    const form = document.getElementById('toolForm');
    const progressWrap = document.getElementById('progressWrap');
    const player = document.getElementById('player');
    const outputText = document.getElementById('outputText');

    form.addEventListener('submit', async (e) => {
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
        if (!pdf) { alert('Please choose a PDF.'); progressWrap.classList.add('hidden'); return; }
        if (pdf.size > maxFileSize) { alert('PDF file is too large (max 10MB).'); progressWrap.classList.add('hidden'); return; }
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
        audio_translate: '/audio-to-translate'
      };

      try {
        const res = await fetch(endpoints[m], { method: 'POST', body: fd });
        if (!res.ok) {
          const msg = await res.text();
          alert(`Error: ${msg}`);
          progressWrap.classList.add('hidden');
          return;
        }

        if (m === 'pdf_audio' || m === 'pdf_translate_audio') {
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
    tmp_in = None
    try:
        audio = request.files.get('audio')
        stt_lang = request.form.get('stt_lang', 'en-US')
        if not audio:
            return "No audio uploaded", 400
        check_file_size(audio)
        ext = '.' + audio.filename.rsplit('.', 1)[-1] if '.' in audio.filename else '.tmp'
        tmp_in = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        audio.save(tmp_in.name)
        tmp_in.close()
        text = stt_google(tmp_in.name, language=stt_lang)
        return jsonify({"text": text})
    except Exception as e:
        return str(e), 400
    finally:
        if tmp_in:
            try:
                os.unlink(tmp_in.name)
            except Exception as e:
                logging.error(f"Failed to delete temp file {tmp_in.name}: {e}")

@app.route('/audio-to-translate', methods=['POST'])
def audio_to_translate():
    tmp_in = None
    try:
        audio = request.files.get('audio')
        stt_lang = request.form.get('stt_lang', 'en-US')
        target = request.form.get('lang', 'en')
        if not audio:
            return "No audio uploaded", 400
        check_file_size(audio)
        ext = '.' + audio.filename.rsplit('.', 1)[-1] if '.' in audio.filename else '.tmp'
        tmp_in = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        audio.save(tmp_in.name)
        tmp_in.close()
        text = stt_google(tmp_in.name, language=stt_lang)
        translated = GoogleTranslator(source='auto', target=target).translate(text)
        return jsonify({"text": text, "translated_text": translated})
    except Exception as e:
        return str(e), 400
    finally:
        if tmp_in:
            try:
                os.unlink(tmp_in.name)
            except Exception as e:
                logging.error(f"Failed to delete temp file {tmp_in.name}: {e}")

if __name__ == '__main__':
    # Run Flask app (Render sets PORT via env var)
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
  
