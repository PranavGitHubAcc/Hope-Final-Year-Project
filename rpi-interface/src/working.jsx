import { useState, useRef } from 'react';

function App() {
  const [isRecording, setIsRecording] = useState(false);
  const [audioUrl, setAudioUrl] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [apiResponse, setApiResponse] = useState('');
  const [isSpeaking, setIsSpeaking] = useState(false);
  
  const mediaRecorder = useRef(null);
  const streamRef = useRef(null);
  const utteranceRef = useRef(null);
  
  // Configuration
  const API_URL = 'https://sg2c12sl-3000.inc1.devtunnels.ms/api/process_audio';
  const USER_ID = 'user1';
  const SESSION_ID = 'session123';

  const speakText = async (text) => {
    if (!text || isSpeaking || !('speechSynthesis' in window)) return;
    
    try {
      setIsSpeaking(true);
      
      // Stop any ongoing speech
      window.speechSynthesis.cancel();
      
      const utterance = new SpeechSynthesisUtterance(text);
      utteranceRef.current = utterance;
      
      // Configure voice (try to get a good English voice)
      const voices = window.speechSynthesis.getVoices();
      const preferredVoice = voices.find(voice => 
        voice.lang.startsWith('en') && voice.name.includes('Google')
      ) || voices.find(voice => voice.lang.startsWith('en'));
      
      if (preferredVoice) {
        utterance.voice = preferredVoice;
      }
      
      utterance.rate = 0.9;
      utterance.pitch = 1;
      utterance.volume = 1;
      
      utterance.onend = () => {
        setIsSpeaking(false);
        utteranceRef.current = null;
      };
      
      utterance.onerror = (error) => {
        console.error('TTS Error:', error);
        setIsSpeaking(false);
        utteranceRef.current = null;
      };
      
      window.speechSynthesis.speak(utterance);
      
    } catch (error) {
      console.error('TTS Error:', error);
      setIsSpeaking(false);
    }
  };

  const stopSpeaking = () => {
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
    setIsSpeaking(false);
    utteranceRef.current = null;
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ 
        audio: { echoCancellation: true, noiseSuppression: true } 
      });
      
      streamRef.current = stream;
      const recorder = new MediaRecorder(stream);
      mediaRecorder.current = recorder;
      
      const chunks = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunks.push(event.data);
      };

      recorder.onstop = async () => {
        const audioBlob = new Blob(chunks, { type: 'audio/wav' });
        setAudioUrl(URL.createObjectURL(audioBlob));
        setIsRecording(false);
        
        await sendAudioToApi(audioBlob);
        
        if (streamRef.current) {
          streamRef.current.getTracks().forEach(track => track.stop());
        }
      };

      recorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error('Microphone error:', err);
      alert('Could not access microphone');
    }
  };

  const stopRecording = () => {
    if (mediaRecorder.current?.state === 'recording') {
      mediaRecorder.current.stop();
    }
  };

  const sendAudioToApi = async (audioBlob) => {
    setIsProcessing(true);
    setApiResponse('Processing...');
    
    try {
      const formData = new FormData();
      formData.append('file', audioBlob, 'recording.wav');
      formData.append('user_id', USER_ID);
      formData.append('session_id', SESSION_ID);
      
      const response = await fetch(API_URL, {
        method: 'POST',
        body: formData,
      });
      
      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }
      
      const data = await response.json();
      const responseText = `Transcription: ${data.transcription}\n\nResponse: ${data.response}`;
      setApiResponse(responseText);
      
      // Auto-speak response
      if (data.response) {
        const cleanText = data.response.replace(/[^\w\s\.\,\?\!\-\'"]/g, '').trim();
        setTimeout(() => speakText(cleanText), 500);
      }
      
    } catch (error) {
      console.error('API error:', error);
      setApiResponse(`Error: ${error.message}`);
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-white rounded-xl shadow-lg p-6 space-y-6">
        
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-800">Voice Assistant</h1>
          <p className="text-gray-600 text-sm mt-1">Record • Process • Speak</p>
        </div>

        <div className="flex justify-center space-x-4">
          {!isRecording ? (
            <button
              onClick={startRecording}
              disabled={isProcessing || isSpeaking}
              className="w-16 h-16 rounded-full bg-red-500 hover:bg-red-600 disabled:bg-gray-400 text-white shadow-lg hover:scale-105 transition-all focus:outline-none focus:ring-2 focus:ring-red-300"
            >
              <svg className="w-8 h-8 mx-auto" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M7 4a3 3 0 016 0v4a3 3 0 11-6 0V4zm4 10.93A7.001 7.001 0 0017 8a1 1 0 10-2 0A5 5 0 015 8a1 1 0 00-2 0 7.001 7.001 0 006 6.93V17H6a1 1 0 100 2h8a1 1 0 100-2h-3v-2.07z" clipRule="evenodd" />
              </svg>
            </button>
          ) : (
            <div className="flex flex-col items-center space-y-3">
              <button
                onClick={stopRecording}
                className="relative w-16 h-16 rounded-full bg-red-600 text-white shadow-lg hover:scale-105 transition-all focus:outline-none"
              >
                <div className="absolute inset-0 bg-red-400 rounded-full animate-ping opacity-75"></div>
                <svg className="relative w-8 h-8 mx-auto" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8 7a1 1 0 00-1 1v4a1 1 0 001 1h4a1 1 0 001-1V8a1 1 0 00-1-1H8z" clipRule="evenodd" />
                </svg>
              </button>
              <span className="text-sm text-red-600 font-medium animate-pulse">Recording...</span>
            </div>
          )}

          {isSpeaking && (
            <button
              onClick={stopSpeaking}
              className="w-16 h-16 rounded-full bg-blue-500 hover:bg-blue-600 text-white shadow-lg hover:scale-105 transition-all focus:outline-none"
            >
              <svg className="w-8 h-8 mx-auto" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M9.383 3.076A1 1 0 0110 4v12a1 1 0 01-1.707.707L4.586 13H2a1 1 0 01-1-1V8a1 1 0 011-1h2.586l3.707-3.707a1 1 0 011.09-.217zM15.657 6.343a1 1 0 011.414 0A9.972 9.972 0 0119 12a9.972 9.972 0 01-1.929 5.657 1 1 0 11-1.414-1.414A7.971 7.971 0 0017 12c0-2.21-.894-4.208-2.343-5.657a1 1 0 010-1.414zm-2.829 2.828a1 1 0 011.415 0A5.983 5.983 0 0115 12a5.984 5.984 0 01-.757 2.828 1 1 0 01-1.415-1.414A3.987 3.987 0 0013 12a3.988 3.988 0 00-.172-1.414 1 1 0 010-1.415z" clipRule="evenodd" />
                <path d="M13 12a1 1 0 11-2 0 1 1 0 012 0z" />
              </svg>
            </button>
          )}
        </div>

        {audioUrl && (
          <div className="space-y-3">
            <h3 className="text-sm font-medium text-gray-700">Recording</h3>
            <audio controls src={audioUrl} className="w-full" />
          </div>
        )}

        {(isProcessing || isSpeaking || apiResponse) && (
          <div className="bg-gray-50 p-4 rounded-lg">
            {isProcessing && (
              <div className="flex items-center space-x-2 text-blue-600">
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600"></div>
                <span className="text-sm">Processing...</span>
              </div>
            )}
            
            {isSpeaking && (
              <div className="flex items-center space-x-2 text-blue-600 mb-2">
                <div className="flex space-x-1">
                  <div className="w-2 h-4 bg-blue-500 rounded animate-pulse"></div>
                  <div className="w-2 h-3 bg-blue-500 rounded animate-pulse" style={{animationDelay: '0.1s'}}></div>
                  <div className="w-2 h-5 bg-blue-500 rounded animate-pulse" style={{animationDelay: '0.2s'}}></div>
                </div>
                <span className="text-sm">Speaking...</span>
              </div>
            )}
            
            {apiResponse && (
              <div className="space-y-2">
                <pre className="text-xs text-gray-700 whitespace-pre-wrap">{apiResponse}</pre>
                {apiResponse.includes('Response:') && !isSpeaking && (
                  <button
                    onClick={() => {
                      const responseText = apiResponse.split('Response: ')[1];
                      if (responseText) {
                        const cleanText = responseText.replace(/[^\w\s\.\,\?\!\-\'"]/g, '').trim();
                        speakText(cleanText);
                      }
                    }}
                    className="px-3 py-1 bg-blue-500 hover:bg-blue-600 text-white text-xs rounded transition-colors"
                  >
                    🔊 Replay
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        <div className="text-center text-xs text-gray-500">
          {!('speechSynthesis' in window) && (
            <p className="text-yellow-600 mb-2">⚠️ TTS not supported in this browser</p>
          )}
          <p>Tap microphone to start recording</p>
        </div>
      </div>
    </div>
  );
}

export default App;