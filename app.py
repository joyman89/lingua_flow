import warnings
warnings.filterwarnings("ignore", category=SyntaxWarning)

import logging
import time
from flask import Flask, request, send_file, jsonify, send_from_directory
from flask_cors import CORS
from PyPDF2 import PdfReader
from PyPDF2.errors import PdfReadError
from deep_translator import GoogleTranslator
from gtts import gTTS
import speech_recognition as sr
from pydub import AudioSegment
import tempfile
import os
from supabase import create_client, Client

# Configure logging
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes
app.secret_key = os.getenv('SECRET_KEY', 'my-secret-key')

# Supabase configuration
SUPABASE_URL = os.getenv('SUPABASE_URL', 'https://lghuxjfcjetcakctrtry.supabase.co')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
if not SUPABASE_KEY:
    raise ValueError("SUPABASE_KEY environment variable is not set")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Constants
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_TEXT_LENGTH = 5000  # Max chars for translation/TTS
VALID_STT_LANGS = ['en-US', 'fr-FR', 'es-ES', 'de-DE', 'my-MM']

INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Lingua Flow – Transform Documents & Audio with AI</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
  <script>
    tailwind.config = {
      theme: {
        extend: {
          colors: {
            brand: {
              50: '#f5f3ff',
              100: '#ede9fe',
              200: '#ddd6fe',
              300: '#c4b5fd',
              400: '#a78bfa',
              500: '#8b5cf6',
              600: '#7c3aed',
              700: '#6b21a8',
              800: '#581c87',
              900: '#3b0764'
            },
            ink: {
              100: '#E6ECEF',
              200: '#C9D4DA',
              300: '#A0AEC0',
              400: '#94A3B8',
              700: '#1F2937',
              900: '#0B1020'
            }
          },
          boxShadow: { glass: '0 10px 30px rgba(0,0,0,.35)' },
          backdropBlur: { xs: '2px' }
        }
      }
    };
    // Initialize Supabase client
    const supabase = window.supabase.createClient('https://lghuxjfcjetcakctrtry.supabase.co', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxnaHV4amZjamV0Y2FrY3RydHJ5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTYxMzk4NTMsImV4cCI6MjA3MTcxNTg1M30.iTqi2LDSsl4PuJ31qyCRtXXPZnld00ZCGUJLEiFOKtc');
    window.supabase = supabase;

    // Refresh session to ensure valid token
    async function refreshSession() {
      const { data: { session }, error } = await supabase.auth.getSession();
      if (error || !session) {
        console.error('Session refresh error:', error);
        showAuthModal('sign-in');
        return null;
      }
      return session.access_token;
    }
  </script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-start: #0f172a;
      --bg-end: #111827;
      --grad-1: #1A1A2E;
      --grad-2: #16213E;
      --logo-grad-1: #6B46C1;
      --logo-grad-2: #4C51BF;
    }
    html, body { height: 100%; }
    body { font-family: 'Inter', system-ui, Segoe UI, Roboto, Helvetica, Arial, sans-serif; }
    .animated-bg {
      background: linear-gradient(120deg, var(--grad-1), var(--grad-2));
      background-size: 400% 400%;
      animation: gradientShift 18s ease infinite;
    }
    @keyframes gradientShift {
      0% { background-position: 0% 50%; }
      50% { background-position: 100% 50%; }
      100% { background-position: 0% 50%; }
    }
    .glass { background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.08); }
    .btn-primary { background: linear-gradient(90deg, var(--logo-grad-1), var(--logo-grad-2)); }
    .btn-primary:hover { filter: brightness(1.1); }
    .modal {
      display: none;
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(0,0,0,0.5);
      z-index: 1000;
      align-items: center;
      justify-content: center;
    }
    .modal-content {
      background: #12192c;
      padding: 20px;
      border-radius: 10px;
      width: 90%;
      max-width: 400px;
      box-shadow: rgba(50, 50, 93, 0.25) 0px 13px 27px -5px, rgba(0, 0, 0, 0.3) 0px 8px 16px -8px;
    }
    .modal-content form {
      margin: 0 auto;
      max-width: 16rem;
    }
    .modal-content form > * + * { margin-top: 1rem; }
    .modal-content form > input {
      border: 0;
      border-bottom: 1px solid white;
      border-radius: 0;
      width: 100%;
      height: 2rem;
      padding: 0 0 0.25rem 0;
      font-size: .8rem;
      color: white;
      background: transparent;
    }
    .modal-content form > input:focus { outline: none; }
    .modal-content form > input::placeholder { color: white; }
    .modal-content form > button {
      margin-top: 2rem;
      border: 0;
      border-radius: 200px;
      width: 100%;
      padding: 0.85rem;
      font-size: 1rem;
      color: #000;
      background: #85FFBD;
    }
    .modal-content form > button:focus { outline: none; }
    .modal-content form > p { text-align: center; color: white; }
    .opposite-btn { cursor: pointer; }
    .flash-error { color: #ff4444; }
    .flash-success { color: #00C851; }
    .sign-up { display: none; }
  </style>
</head>
<body class="animated-bg min-h-screen text-slate-100 flex flex-col">

<!-- Login/Signup Modal -->
<div id="authModal" class="modal">
  <div class="modal-content">
    <div class="text-center mb-4">
      <p>Log in or create a new account.</p>
    </div>
    <!-- Flash Messages -->
    <div id="flashMessages" class="text-center mb-4"></div>
    <!-- Sign Up -->
    <div class="sign-up">
      <form id="signupForm">
        <input type="text" name="name" placeholder="Name" required>
        <input type="email" name="email" placeholder="Email" required>
        <input type="password" name="password" placeholder="Password" required>
        <input type="password" name="confirm" placeholder="Confirm Password" required>
        <button type="submit">Create Account</button>
        <p class="opposite-btn" onclick="toggleAuthForms('sign-in')">Already have an account?</p>
      </form>
    </div>
    <!-- Sign In -->
    <div class="sign-in">
      <form id="loginForm">
        <input type="email" name="email" placeholder="Email" required>
        <input type="password" name="password" placeholder="Password" required>
        <button type="submit">Sign In</button>
        <p class="opposite-btn" id="forgotPasswordLink" onclick="showForgotPassword()">Forgot Password?</p>
      </form>
      <div id="forgotPasswordSection" class="hidden mt-4">
        <form id="forgotPasswordForm">
          <input type="email" id="resetEmail" placeholder="Enter your email" required>
          <button type="submit" class="btn-primary w-full mt-2 rounded-xl py-2 text-white">Reset Password</button>
        </form>
        <p class="opposite-btn mt-2" onclick="toggleAuthForms('sign-in')">Back to Sign In</p>
      </div>
      <p class="opposite-btn" onclick="toggleAuthForms('sign-up')">Don't have an account?</p>
    </div>
  </div>
</div>

  <!-- Header / Nav -->
  <header class="w-full">
    <div class="mx-auto max-w-6xl px-4 py-5 flex items-center justify-between">
      <a href="#" class="flex items-center gap-3 group">
        <img src="/static/logo.png" alt="Logo" class="h-11 w-11 object-contain">
        <div>
          <div class="text-xl font-extrabold tracking-tight leading-6">Lingua Flow</div>
          <div class="text-xs text-slate-300/80 mt-1">Transform • Translate • Speak</div>
        </div>
      </a>
      <div class="flex items-center gap-2">
        <button id="authButton" onclick="showAuthModal('sign-in')" class="btn-primary text-sm px-3 py-1.5 rounded-full shadow">Login</button>
        <span class="text-sm text-slate-300">5+ Languages</span>
      </div>
    </div>
  </header>

  <!-- Hero -->
  <section class="mx-auto max-w-6xl px-4 pb-6">
    <div class="grid lg:grid-cols-2 gap-6 items-stretch">
      <div class="glass rounded-2xl shadow-glass p-6 md:p-8 flex flex-col justify-center">
        <h1 class="text-3xl md:text-4xl font-extrabold leading-tight">
          Transform documents & audio with
          <span class="bg-clip-text text-transparent" style="background-image:linear-gradient(90deg, var(--logo-grad-1), var(--logo-grad-2))">real‑time AI</span>
        </h1>
        <p class="mt-3 text-slate-200/90">Extract, translate, and convert between text and speech in a single, elegant tool. Fast. Accurate. Private.</p>
        <ul class="mt-5 space-y-2 text-sm text-slate-200/90">
          <li class="flex items-start gap-3">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mt-0.5 text-brand-300">
              <path d="M20 6L9 17l-5-5"/>
            </svg>
            PDF text extraction with OCR-ready pipeline
          </li>
          <li class="flex items-start gap-3">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mt-0.5 text-brand-300">
              <path d="M20 6L9 17l-5-5"/>
            </svg>
            Multi‑language translation
          </li>
          <li class="flex items-start gap-3">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mt-0.5 text-brand-300">
              <path d="M20 6L9 17l-5-5"/>
            </svg>
            Natural‑sounding text‑to‑speech
          </li>
          <li class="flex items-start gap-3">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mt-0.5 text-brand-300">
              <path d="M20 6L9 17l-5-5"/>
            </svg>
            Accurate speech recognition
          </li>
        </ul>
      </div>

      <!-- Card: Tool Form -->
      <div class="glass rounded-2xl shadow-glass p-6 md:p-8">
        <form id="toolForm" class="space-y-5" enctype="multipart/form-data">
          <!-- Mode -->
          <div>
            <label class="block text-sm font-semibold mb-2" for="mode">Processing Mode</label>
            <div class="relative">
              <select id="mode" name="mode" class="w-full appearance-none rounded-xl bg-slate-900/60 border border-white/10 px-4 py-3 pr-10 focus:outline-none focus:ring-2 focus:ring-brand-400">
                <option value="pdf_audio">PDF → Audio • Convert PDF text to speech</option>
                <option value="pdf_translate">PDF → Translate • Extract & translate text</option>
                <option value="pdf_translate_audio">PDF → Translate → Audio • Translate then speech</option>
                <option value="audio_text">Audio → Text • Speech to text</option>
                <option value="audio_translate">Audio → Translate • STT and translate</option>
                <option value="audio_audio">Audio → Audio • Speak back in target language</option>
              </select>
              <div class="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-4">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-slate-300"><path d="M6 9l6 6 6-6"/></svg>
              </div>
            </div>
          </div>
          <!-- Target Language -->
          <div id="langDiv" class="hidden">
            <label class="block text-sm font-semibold mb-2" for="lang">Target Language</label>
            <div class="relative">
              <select id="lang" name="lang" class="w-full appearance-none rounded-xl bg-slate-900/60 border border-white/10 px-4 py-3 pr-10 focus:outline-none focus:ring-2 focus:ring-brand-400">
                <option value="en">English</option>
                <option value="my">Myanmar</option>
                <option value="fr">French</option>
                <option value="es">Spanish</option>
                <option value="de">German</option>
              </select>
              <div class="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-4">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-slate-300"><path d="M6 9l6 6 6-6"/></svg>
              </div>
            </div>
          </div>
          <!-- PDF Input -->
          <div id="pdfInput">
            <label class="block text-sm font-semibold mb-2" for="pdf">1. Upload PDF</label>
            <label class="group flex items-center justify-between gap-4 rounded-xl border border-dashed border-white/15 bg-slate-900/50 p-4 hover:border-brand-300 cursor-pointer">
              <div class="flex items-center gap-3">
                <div class="rounded-lg p-2" style="background:linear-gradient(90deg, var(--logo-grad-1), var(--logo-grad-2))">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                </div>
                <div>
                  <div class="text-sm font-semibold">Drag & drop your PDF here</div>
                  <div class="text-xs text-slate-300">or click to browse • Max 10MB</div>
                </div>
              </div>
              <input id="pdf" name="pdf" type="file" accept="application/pdf" class="sr-only" />
              <span id="pdfName" class="text-xs text-slate-300">No file chosen</span>
            </label>
          </div>
          <!-- Audio Input -->
          <div id="audioInput" class="hidden">
            <label class="block text-sm font-semibold mb-2" for="audio">1. Upload Audio</label>
            <label class="group flex items-center justify-between gap-4 rounded-xl border border-dashed border-white/15 bg-slate-900/50 p-4 hover:border-brand-300 cursor-pointer">
              <div class="flex items-center gap-3">
                <div class="rounded-lg p-2" style="background:linear-gradient(90deg, var(--logo-grad-1), var(--logo-grad-2))">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><path d="M12 1v11"/><path d="M5 10a7 7 0 0 0 14 0"/><path d="M8 21h8"/></svg>
                </div>
                <div>
                  <div class="text-sm font-semibold">Drag & drop your audio</div>
                  <div class="text-xs text-slate-300">MP3, WAV, M4A, OGG • Max 10MB</div>
                </div>
              </div>
              <input id="audio" name="audio" type="file" accept="audio/*" class="sr-only" />
              <span id="audioName" class="text-xs text-slate-300">No file chosen</span>
            </label>
          </div>
          <!-- STT language -->
          <div id="sttLangRow" class="hidden">
            <label class="block text-sm font-semibold mb-2" for="stt_lang">Speech Language (for STT)</label>
            <div class="relative">
              <select id="stt_lang" name="stt_lang" class="w-full appearance-none rounded-xl bg-slate-900/60 border border-white/10 px-4 py-3 pr-10 focus:outline-none focus:ring-2 focus:ring-brand-400">
                <option value="en-US">English (US)</option>
                <option value="fr-FR">French</option>
                <option value="es-ES">Spanish</option>
                <option value="de-DE">German</option>
                <option value="my-MM">Myanmar</option>
              </select>
              <div class="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-4">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-slate-300"><path d="M6 9l6 6 6-6"/></svg>
              </div>
            </div>
          </div>
          <!-- Submit -->
          <button type="submit" class="btn-primary w-full rounded-xl py-3.5 font-semibold text-white shadow-lg active:scale-[.99] transition">2. Start Processing</button>
          <!-- Progress -->
          <div id="progressWrap" class="hidden h-2 w-full overflow-hidden rounded bg-white/10">
            <div class="h-full w-0 bg-white/60 animate-[loader_2s_ease_infinite]"></div>
          </div>
          <style>
            @keyframes loader { 0% { width: 0; } 50% { width: 80%; } 100% { width: 100%; } }
          </style>
          <!-- Output -->
          <div class="space-y-3 pt-2">
            <audio id="player" class="hidden w-full" controls></audio>
            <textarea id="outputText" class="hidden w-full min-h-[140px] rounded-xl bg-slate-900/60 border border-white/10 p-3 text-sm" placeholder="Results will appear here"></textarea>
          </div>
        </form>
      </div>
    </div>
  </section>

  <!-- Features band -->
  <section class="mx-auto max-w-6xl px-4 pb-10">
    <div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <div class="glass rounded-xl p-4 flex items-start gap-3">
        <div class="rounded-md p-2" style="background:linear-gradient(90deg, var(--logo-grad-1), var(--logo-grad-2))">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>
        </div>
        <div>
          <div class="font-semibold">PDF Extraction</div>
          <div class="text-xs text-slate-300">Pull clean text from complex PDFs.</div>
        </div>
      </div>
      <div class="glass rounded-xl p-4 flex items-start gap-3">
        <div class="rounded-md p-2" style="background:linear-gradient(90deg, var(--logo-grad-1), var(--logo-grad-2))">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><path d="M5 12h14"/><path d="M12 5l7 7-7 7"/></svg>
        </div>
        <div>
          <div class="font-semibold">Translate</div>
          <div class="text-xs text-slate-300">20+ languages, auto‑detect.</div>
        </div>
      </div>
      <div class="glass rounded-xl p-4 flex items-start gap-3">
        <div class="rounded-md p-2" style="background:linear-gradient(90deg, var(--logo-grad-1), var(--logo-grad-2))">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><path d="M12 1v11"/><path d="M5 10a7 7 0 0 0 14 0"/><path d="M8 21h8"/></svg>
        </div>
        <div>
          <div class="font-semibold">Text‑to‑Speech</div>
          <div class="text-xs text-slate-300">Natural voices, quick output.</div>
        </div>
      </div>
      <div class="glass rounded-xl p-4 flex items-start gap-3">
        <div class="rounded-md p-2" style="background:linear-gradient(90deg, var(--logo-grad-1), var(--logo-grad-2))">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><path d="M12 5v6"/><rect x="9" y="11" width="6" height="8" rx="2"/></svg>
        </div>
        <div>
          <div class="font-semibold">Speech‑to‑Text</div>
          <div class="text-xs text-slate-300">Accurate recognition.</div>
        </div>
      </div>
    </div>
  </section>

  <!-- Footer -->
  <footer class="mt-auto border-t border-white/10">
    <div class="mx-auto max-w-6xl px-4 py-6 text-center text-sm text-slate-300">
      © A&T Group at Strategy First AI Hackathon 2025
    </div>
  </footer>

  <!-- App Logic -->
  <script>
    const modeSel = document.getElementById('mode');
    const pdfInput = document.getElementById('pdfInput');
    const audioInput = document.getElementById('audioInput');
    const sttLangRow = document.getElementById('sttLangRow');
    const langDiv = document.getElementById('langDiv');
    const progressWrap = document.getElementById('progressWrap');
    const player = document.getElementById('player');
    const outputText = document.getElementById('outputText');
    const pdfFileInput = document.getElementById('pdf');
    const audioFileInput = document.getElementById('audio');
    const pdfName = document.getElementById('pdfName');
    const audioName = document.getElementById('audioName');
    const authModal = document.getElementById('authModal');
    const signupForm = document.getElementById('signupForm');
    const loginForm = document.getElementById('loginForm');
    const forgotPasswordForm = document.getElementById('forgotPasswordForm');
    const flashMessages = document.getElementById('flashMessages');
    const authButton = document.getElementById('authButton');
    let isAuthenticated = false;

    // Check authentication status on load
    async function checkAuth() {
      const { data: { session }, error } = await supabase.auth.getSession();
      if (error) console.error('Auth check error:', error.message);
      isAuthenticated = !!session;
      authButton.style.display = isAuthenticated ? 'none' : 'inline-block';
      console.log('Auth checked, isAuthenticated:', isAuthenticated);
    }

    function updateFormVisibility() {
      const m = modeSel.value;
      const pdfNeeded = (m === 'pdf_audio' || m === 'pdf_translate' || m === 'pdf_translate_audio');
      const audioNeeded = (m === 'audio_text' || m === 'audio_translate' || m === 'audio_audio');
      const translationNeeded = (m === 'pdf_translate' || m === 'pdf_translate_audio' || m === 'audio_translate' || m === 'audio_audio');
      pdfInput.classList.toggle('hidden', !pdfNeeded);
      audioInput.classList.toggle('hidden', !audioNeeded);
      sttLangRow.classList.toggle('hidden', !audioNeeded);
      langDiv.classList.toggle('hidden', !translationNeeded);
    }

    function updateFileStatus() {
      const p = pdfFileInput?.files?.[0];
      const a = audioFileInput?.files?.[0];
      if (p) pdfName.textContent = p.name; else pdfName.textContent = 'No file chosen';
      if (a) audioName.textContent = a.name; else audioName.textContent = 'No file chosen';
    }

    function showAuthModal(mode) {
      authModal.style.display = 'flex';
      document.querySelector('.sign-up').style.display = mode === 'sign-up' ? 'block' : 'none';
      document.querySelector('.sign-in').style.display = mode === 'sign-in' ? 'block' : 'none';
      flashMessages.innerHTML = '';
    }

    function toggleAuthForms(mode) {
      document.querySelector('.sign-up').style.display = mode === 'sign-up' ? 'block' : 'none';
      document.querySelector('.sign-in').style.display = mode === 'sign-in' ? 'block' : 'none';
    }

    function showForgotPassword() {
      document.querySelector('.sign-in form').classList.add('hidden');
      document.getElementById('forgotPasswordSection').classList.remove('hidden');
      flashMessages.innerHTML = '';
    }

    signupForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const fd = new FormData(signupForm);
      const name = fd.get('name');
      const email = fd.get('email');
      const password = fd.get('password');
      const confirm = fd.get('confirm');
      if (password !== confirm) {
        flashMessages.innerHTML = '<p class="flash-error">Passwords do not match</p>';
        return;
      }
      try {
        console.log('Signing up with:', email);
        const { data, error } = await supabase.auth.signUp({
          email,
          password,
          options: {
            data: { name },
            emailRedirectTo: 'https://lingua-flow.onrender.com'
          }
        });
        if (error) {
          flashMessages.innerHTML = `<p class="flash-error">${error.message}</p>`;
          console.error('Signup error:', error);
        } else {
          flashMessages.innerHTML = '<p class="flash-success">Account created! Check your email for a confirmation link.</p>';
          await supabase.from('users').insert({ id: data.user.id, name, email });
        }
      } catch (e) {
        flashMessages.innerHTML = `<p class="flash-error">Network error: ${e.message}</p>`;
        console.error('Signup network error:', e);
      }
    });

    loginForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const fd = new FormData(loginForm);
      const email = fd.get('email');
      const password = fd.get('password');
      try {
        console.log('Logging in with:', email);
        const { data, error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) {
          flashMessages.innerHTML = `<p class="flash-error">${error.message}</p>`;
          console.error('Login error:', error);
        } else {
          flashMessages.innerHTML = '<p class="flash-success">Logged in successfully!</p>';
          checkAuth();
          setTimeout(() => { authModal.style.display = 'none'; }, 1000);
        }
      } catch (e) {
        flashMessages.innerHTML = `<p class="flash-error">Network error: ${e.message}</p>`;
        console.error('Login network error:', e);
      }
    });

    forgotPasswordForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const email = document.getElementById('resetEmail').value;
      try {
        console.log('Requesting password reset for:', email);
        const { data, error } = await supabase.auth.resetPasswordForEmail(email, {
          redirectTo: 'https://lingua-flow.onrender.com'
        });
        if (error) {
          flashMessages.innerHTML = `<p class="flash-error">${error.message}</p>`;
          console.error('Password reset error:', error);
        } else {
          flashMessages.innerHTML = '<p class="flash-success">Password reset link sent! Check your email.</p>';
          setTimeout(() => { document.getElementById('forgotPasswordSection').classList.add('hidden'); document.querySelector('.sign-in form').classList.remove('hidden'); }, 2000);
        }
      } catch (e) {
        flashMessages.innerHTML = `<p class="flash-error">Network error: ${e.message}</p>`;
        console.error('Password reset network error:', e);
      }
    });

    document.getElementById('toolForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      if (!isAuthenticated) {
        showAuthModal('sign-in');
        return;
      }
      progressWrap.classList.remove('hidden');
      player.classList.add('hidden');
      outputText.classList.add('hidden');
      outputText.value = '';

      const m = modeSel.value;
      const lang = document.getElementById('lang').value;
      const sttLang = document.getElementById('stt_lang').value;
      const maxFileSize = 10 * 1024 * 1024;

      const fd = new FormData();
      if (m.startsWith('pdf')) {
        const pdf = pdfFileInput.files[0];
        if (!pdf) { alert('Please choose a PDF.'); progressWrap.classList.add('hidden'); return; }
        if (pdf.size > maxFileSize) { alert('Document is too large (max 10MB).'); progressWrap.classList.add('hidden'); return; }
        fd.append('pdf', pdf);
        if (m !== 'pdf_audio') fd.append('lang', lang);
      } else {
        const audio = audioFileInput.files[0];
        if (!audio) { alert('Please choose an audio file.'); progressWrap.classList.add('hidden'); return; }
        if (audio.size > maxFileSize) { alert('Audio is too large (max 10MB).'); progressWrap.classList.add('hidden'); return; }
        fd.append('audio', audio);
        if (m !== 'audio_text') fd.append('lang', lang);
        fd.append('stt_lang', sttLang);
      }

      const endpoints = {
        pdf_audio: 'https://lingua-flow.onrender.com/pdf-to-audio',
        pdf_translate: 'https://lingua-flow.onrender.com/pdf-to-translate',
        pdf_translate_audio: 'https://lingua-flow.onrender.com/pdf-to-translate-audio',
        audio_text: 'https://lingua-flow.onrender.com/audio-to-text',
        audio_translate: 'https://lingua-flow.onrender.com/audio-to-translate',
        audio_audio: 'https://lingua-flow.onrender.com/audio-to-audio'
      };

      try {
        const token = await refreshSession();
        if (!token) {
          alert('Session expired. Please log in again.');
          progressWrap.classList.add('hidden');
          return;
        }
        console.log('Sending JWT Token:', token);
        const res = await fetch(endpoints[m], {
          method: 'POST',
          body: fd,
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!res.ok) {
          const msg = await res.text();
          alert(`Error: ${msg}`);
          progressWrap.classList.add('hidden');
          return;
        }

        // Log to history table
        const { data: { session } } = await supabase.auth.getSession();
        const historyEntry = {
          user_id: session.user.id,
          mode: m,
          input_file: m.startsWith('pdf') ? pdfFileInput.files[0]?.name : audioFileInput.files[0]?.name,
          target_language: m !== 'pdf_audio' && m !== 'audio_text' ? lang : null,
          stt_language: m.startsWith('audio') ? sttLang : null
        };

        if (m === 'pdf_audio' || m === 'pdf_translate_audio' || m === 'audio_audio') {
          const blob = await res.blob();
          const url = URL.createObjectURL(blob);
          player.src = url;
          player.classList.remove('hidden');
          historyEntry.output_result = 'Audio output';
        } else {
          const data = await res.json();
          const text = data.translated_text || data.text || JSON.stringify(data);
          outputText.value = text;
          outputText.classList.remove('hidden');
          historyEntry.output_result = text;
        }

        await supabase.from('history').insert(historyEntry);
      } catch (e) {
        alert(`Network error: ${e.message}`);
      }

      progressWrap.classList.add('hidden');
    });

    // Close modal when clicking outside
    authModal.addEventListener('click', (e) => {
      if (e.target === authModal) {
        authModal.style.display = 'none';
        flashMessages.innerHTML = '';
      }
    });

    modeSel.addEventListener('change', updateFormVisibility);
    pdfFileInput.addEventListener('change', updateFileStatus);
    audioFileInput.addEventListener('change', updateFileStatus);
    updateFormVisibility();
    checkAuth();
  </script>
</body>
</html>
"""

# Debug route to check environment variables
@app.route('/debug-env')
def debug_env():
    return jsonify({
        'SUPABASE_KEY': bool(os.getenv('SUPABASE_KEY')),
        'SUPABASE_URL': os.getenv('SUPABASE_URL'),
        'SECRET_KEY': os.getenv('SECRET_KEY'),
        'PORT': os.getenv('PORT')
    })

# Middleware to verify JWT
def verify_jwt():
    auth_header = request.headers.get('Authorization')
    logging.debug(f"Authorization header: {auth_header}")
    if not auth_header or not auth_header.startswith('Bearer '):
        return None, "Missing or invalid Authorization header"
    token = auth_header.split(' ')[1]
    logging.debug(f"JWT Token: {token}")
    try:
        response = supabase.auth.get_user(token)
        logging.debug(f"Supabase get_user response: {response}")
        if response.user:
            return response.user.id, None
        return None, "Invalid token or user not found"
    except Exception as e:
        logging.error(f"JWT verification error: {str(e)}")
        return None, f"Authentication error: {str(e)}"

# Helper Functions
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

def convert_to_wav(audio_file) -> str:
    tf = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
    try:
        audio = AudioSegment.from_file(audio_file)
        audio = audio.set_channels(1).set_frame_rate(16000)
        audio.export(tf.name, format='wav')
    except Exception as e:
        raise ValueError(f"Audio conversion failed: {str(e)}")
    return tf.name

def stt_google(audio_path: str, language: str = 'en-US') -> str:
    language = validate_stt_lang(language)
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(audio_path) as source:
            audio_data = recognizer.record(source)
        return recognizer.recognize_google(audio_data, language=language)
    except sr.UnknownValueError:
        raise ValueError("Could not understand the audio.")
    except sr.RequestError as e:
        raise ValueError(f"Speech service error: {e}")
    finally:
        try:
            os.unlink(audio_path)
        except Exception as e:
            logging.error(f"Failed to delete temp file {audio_path}: {e}")

# Routes
@app.route('/')
def index():
    return INDEX_HTML

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

@app.route('/pdf-to-audio', methods=['POST'])
def pdf_to_audio():
    user_id, error = verify_jwt()
    if error:
        return jsonify({"error": error}), 401
    mp3_path = None
    try:
        pdf = request.files.get('pdf')
        lang = request.form.get('lang', 'en')
        if not pdf:
            return jsonify({"error": "No PDF uploaded"}), 400
        text = extract_text_from_pdf(pdf)
        mp3_path = tts_to_tempfile(text, lang)
        supabase.table('history').insert({
            'user_id': user_id,
            'mode': 'pdf_audio',
            'input_file': pdf.filename,
            'output_result': 'Audio output',
            'target_language': lang
        }).execute()
        return send_file(mp3_path, mimetype='audio/mpeg', as_attachment=True, download_name='audiobook.mp3')
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    finally:
        if mp3_path:
            try:
                os.unlink(mp3_path)
            except Exception as e:
                logging.error(f"Failed to delete temp file {mp3_path}: {e}")

@app.route('/pdf-to-translate', methods=['POST'])
def pdf_to_translate():
    user_id, error = verify_jwt()
    if error:
        return jsonify({"error": error}), 401
    try:
        pdf = request.files.get('pdf')
        target = request.form.get('lang', 'en')
        if not pdf:
            return jsonify({"error": "No PDF uploaded"}), 400
        text = extract_text_from_pdf(pdf)
        translated = GoogleTranslator(source='auto', target=target).translate(text)
        time.sleep(0.2)
        supabase.table('history').insert({
            'user_id': user_id,
            'mode': 'pdf_translate',
            'input_file': pdf.filename,
            'output_result': translated,
            'target_language': target
        }).execute()
        return jsonify({"translated_text": translated})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/pdf-to-translate-audio', methods=['POST'])
def pdf_to_translate_audio():
    user_id, error = verify_jwt()
    if error:
        return jsonify({"error": error}), 401
    mp3_path = None
    try:
        pdf = request.files.get('pdf')
        target = request.form.get('lang', 'en')
        if not pdf:
            return jsonify({"error": "No PDF uploaded"}), 400
        text = extract_text_from_pdf(pdf)
        translated = GoogleTranslator(source='auto', target=target).translate(text)
        time.sleep(0.2)
        mp3_path = tts_to_tempfile(translated, target)
        supabase.table('history').insert({
            'user_id': user_id,
            'mode': 'pdf_translate_audio',
            'input_file': pdf.filename,
            'output_result': 'Audio output',
            'target_language': target
        }).execute()
        return send_file(mp3_path, mimetype='audio/mpeg', as_attachment=True, download_name='translated_audiobook.mp3')
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    finally:
        if mp3_path:
            try:
                os.unlink(mp3_path)
            except Exception as e:
                logging.error(f"Failed to delete temp file {mp3_path}: {e}")

@app.route('/audio-to-text', methods=['POST'])
def audio_to_text():
    user_id, error = verify_jwt()
    if error:
        return jsonify({"error": error}), 401
    try:
        audio = request.files.get('audio')
        stt_lang = request.form.get('stt_lang', 'en-US')
        if not audio:
            return jsonify({"error": "No audio uploaded"}), 400
        check_file_size(audio)
        wav_path = convert_to_wav(audio)
        text = stt_google(wav_path, language=stt_lang)
        supabase.table('history').insert({
            'user_id': user_id,
            'mode': 'audio_text',
            'input_file': audio.filename,
            'output_result': text,
            'stt_language': stt_lang
        }).execute()
        return jsonify({"text": text})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/audio-to-translate', methods=['POST'])
def audio_to_translate():
    user_id, error = verify_jwt()
    if error:
        return jsonify({"error": error}), 401
    try:
        audio = request.files.get('audio')
        stt_lang = request.form.get('stt_lang', 'en-US')
        target = request.form.get('lang', 'en')
        if not audio:
            return jsonify({"error": "No audio uploaded"}), 400
        check_file_size(audio)
        wav_path = convert_to_wav(audio)
        text = stt_google(wav_path, language=stt_lang)
        translated = GoogleTranslator(source='auto', target=target).translate(text)
        time.sleep(0.2)
        supabase.table('history').insert({
            'user_id': user_id,
            'mode': 'audio_translate',
            'input_file': audio.filename,
            'output_result': translated,
            'target_language': target,
            'stt_language': stt_lang
        }).execute()
        return jsonify({"text": text, "translated_text": translated})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/audio-to-audio', methods=['POST'])
def audio_to_audio():
    user_id, error = verify_jwt()
    if error:
        return jsonify({"error": error}), 401
    mp3_path = None
    try:
        audio = request.files.get('audio')
        stt_lang = request.form.get('stt_lang', 'en-US')
        target_lang = request.form.get('lang', 'en')
        if not audio:
            return jsonify({"error": "No audio uploaded"}), 400
        check_file_size(audio)
        wav_path = convert_to_wav(audio)
        text = stt_google(wav_path, language=stt_lang)
        translated = GoogleTranslator(source='auto', target=target_lang).translate(text)
        time.sleep(0.2)
        mp3_path = tts_to_tempfile(translated, target_lang)
        supabase.table('history').insert({
            'user_id': user_id,
            'mode': 'audio_audio',
            'input_file': audio.filename,
            'output_result': 'Audio output',
            'target_language': target_lang,
            'stt_language': stt_lang
        }).execute()
        return send_file(mp3_path, mimetype='audio/mpeg', as_attachment=True, download_name='translated_audio.mp3')
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    finally:
        if mp3_path:
            try:
                os.unlink(mp3_path)
            except Exception as e:
                logging.error(f"Failed to delete temp file {mp3_path}: {e}")

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
