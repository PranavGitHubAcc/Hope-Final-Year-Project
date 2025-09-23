import { useState, useRef } from 'react';

// Azure Speech SDK (you'll need to install: npm install microsoft-cognitiveservices-speech-sdk)
import * as speechsdk from 'microsoft-cognitiveservices-speech-sdk';

// Token utility function using fetch instead of axios
async function getTokenOrRefresh() {
  // Simple in-memory token storage (replace with proper cookie implementation if needed)
  const tokenKey = 'speech-token';
  const cachedToken = sessionStorage.getItem(tokenKey);
  
  if (cachedToken) {
    const [region, token] = cachedToken.split(':');
    console.log('Token fetched from cache: ' + token);
    return { authToken: token, region: region };
  }

  try {
    const res = await fetch('/api/get-speech-token');
    if (!res.ok) {
      throw new Error(`HTTP error! status: ${res.status}`);
    }
    const data = await res.json();
    const token = data.token;
    const region = data.region;
    
    // Cache token for 9 minutes (540 seconds)
    sessionStorage.setItem(tokenKey, region + ':' + token);
    console.log('Token fetched from back-end: ' + token);
    return { authToken: token, region: region };
  } catch (err) {
    console.error('Error fetching token:', err);
    return { authToken: null, error: err.message };
  }
}

function App() {
  const [isRecording, setIsRecording] = useState(false);
  const [audioUrl, setAudioUrl] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [apiResponse, setApiResponse] = useState('');
  const [isSpeaking, setIsSpeaking] = useState(false);
  
  const mediaRecorder = useRef(null);
  const streamRef = useRef(null);
  const synthesizerRef = useRef(null);
  const audioPlayerRef = useRef(null);
  
  // Configuration
  const API_URL = 'http://localhost:3000/api/process_audio';
  const USER_ID = 'user1';
  const SESSION_ID = 'session123';

  const speakText = async (text) => {
    if (!text || isSpeaking) return;
    
    try {
      setIsSpeaking(true);
      
      // Stop any ongoing speech
      if (synthesizerRef.current) {
        synthesizerRef.current.close();
        synthesizerRef.current = null;
      }
      if (audioPlayerRef.current) {
        audioPlayerRef.current.pause();
        audioPlayerRef.current = null;
      }

      const SPEECH_KEY = 'FnZ2OxW0baDFFY4ioEaQwU6s59jMq9jXD0tl7hjae7RlcwKtlLVuJQQJ99BHACYeBjFXJ3w3AAAAACOG2zA1'; // Replace with your actual key
      const SPEECH_REGION = 'eastus'; // Replace with your region (e.g., 'eastus')
      
      // Configure Azure Speech with subscription key
      const speechConfig = speechsdk.SpeechConfig.fromSubscription(
        SPEECH_KEY, 
        SPEECH_REGION
      );
      
      // Set voice (you can customize this)
      speechConfig.speechSynthesisVoiceName = "en-US-AvaNeural";
      
      // Create audio destination
      const audioPlayer = new speechsdk.SpeakerAudioDestination();
      audioPlayerRef.current = audioPlayer;
      const audioConfig = speechsdk.AudioConfig.fromSpeakerOutput(audioPlayer);
      
      // Create synthesizer
      const synthesizer = new speechsdk.SpeechSynthesizer(speechConfig, audioConfig);
      synthesizerRef.current = synthesizer;
      
      console.log('Starting Azure TTS for:', text);
      
      synthesizer.speakTextAsync(
        text,
        (result) => {
          if (result.reason === speechsdk.ResultReason.SynthesizingAudioCompleted) {
            console.log('Azure TTS completed successfully');
          } else if (result.reason === speechsdk.ResultReason.Canceled) {
            console.error('Azure TTS cancelled:', result.errorDetails);
          }
          
          // Cleanup
          synthesizer.close();
          synthesizerRef.current = null;
          audioPlayerRef.current = null;
          setIsSpeaking(false);
        },
        (error) => {
          console.error('Azure TTS error:', error);
          synthesizer.close();
          synthesizerRef.current = null;
          audioPlayerRef.current = null;
          setIsSpeaking(false);
        }
      );
      
    } catch (error) {
      console.error('TTS Error:', error);
      setIsSpeaking(false);
    }
  };

  const stopSpeaking = () => {
    if (synthesizerRef.current) {
      synthesizerRef.current.close();
      synthesizerRef.current = null;
    }
    if (audioPlayerRef.current) {
      audioPlayerRef.current.pause();
      audioPlayerRef.current = null;
    }
    setIsSpeaking(false);
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
      
      // Auto-speak response using Azure TTS
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

  // Enhanced Eye Animation Component
  const EyeAnimation = () => {
    const getEyeState = () => {
      if (isRecording) {
        return {
          leftAnimation: 'listening-left 3s ease-in-out infinite',
          rightAnimation: 'listening-right 3s ease-in-out infinite',
          brightness: '1.2'
        };
      }
      if (isSpeaking) {
        return {
          leftAnimation: 'speaking 1.2s ease-in-out infinite',
          rightAnimation: 'speaking 1.2s ease-in-out infinite',
          brightness: '1.3'
        };
      }
      if (isProcessing) {
        return {
          leftAnimation: 'thinking 2.5s ease-in-out infinite',
          rightAnimation: 'thinking 2.5s ease-in-out infinite',
          brightness: '0.9'
        };
      }
      // Idle state - curious animation
      return {
        leftAnimation: 'curious-left 8s ease-in-out infinite',
        rightAnimation: 'curious-right 8s ease-in-out infinite',
        brightness: '1'
      };
    };

    const eyeState = getEyeState();

    return (
      <>
        <style jsx>{`
          .left-eye {
            animation: ${eyeState.leftAnimation};
          }
          
          .right-eye {
            animation: ${eyeState.rightAnimation};
          }
          
          /* Listening animations */
          @keyframes listening-left {
            0%, 100% { transform: translateX(0px) scale(1); }
            50% { transform: translateX(-8px) scale(1.05); }
          }
          
          @keyframes listening-right {
            0%, 100% { transform: translateX(0px) scale(1); }
            50% { transform: translateX(8px) scale(1.05); }
          }
          
          /* Speaking animations */
          @keyframes speaking {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.1); }
          }
          
          /* Thinking animations */
          @keyframes thinking {
            0%, 100% { opacity: 0.8; }
            50% { opacity: 1; }
          }
          
          /* Curious idle animations */
          @keyframes curious-left {
            0% { transform: scale(1) translateY(0px); }
            15% { transform: scale(0.8) translateY(-3px); }
            30% { transform: scale(1) translateY(0px); }
            45% { transform: scale(1) translateX(-5px); }
            60% { transform: scale(1.1) translateX(0px) translateY(-2px); }
            75% { transform: scale(1) translateX(3px); }
            85% { transform: scale(0.9) translateX(0px) translateY(1px); }
            100% { transform: scale(1) translateY(0px); }
          }
          
          @keyframes curious-right {
            0% { transform: scale(1) translateY(0px); }
            10% { transform: scale(1) translateY(0px); }
            25% { transform: scale(1.2) translateY(-4px); }
            40% { transform: scale(1) translateY(0px); }
            55% { transform: scale(0.7) translateX(4px); }
            70% { transform: scale(1) translateX(0px) translateY(-1px); }
            80% { transform: scale(1.05) translateX(-2px); }
            90% { transform: scale(1) translateX(0px) translateY(1px); }
            100% { transform: scale(1) translateY(0px); }
          }
        `}</style>
        
        <div className="flex justify-center items-center space-x-8 py-8">
          {/* Left Eye - Click to record */}
          <div
            onClick={!isRecording ? startRecording : stopRecording}
            className="left-eye cursor-pointer transform transition-all duration-300 hover:scale-105"
            style={{
              width: '80px',
              height: '80px',
              backgroundColor: '#00ffff',
              borderRadius: '16px',
              filter: `brightness(${eyeState.brightness}) drop-shadow(0 0 12px rgba(0, 255, 255, 0.5))`,
              transformOrigin: 'center'
            }}
          />
          
          {/* Right Eye - Decorative */}
          <div
            className="right-eye"
            style={{
              width: '80px',
              height: '80px',
              backgroundColor: '#00ffff',
              borderRadius: '16px',
              filter: `brightness(${eyeState.brightness}) drop-shadow(0 0 12px rgba(0, 255, 255, 0.5))`,
              transformOrigin: 'center'
            }}
          />
        </div>
      </>
    );
  };

  return (
    <div className="min-h-screen bg-black flex flex-col items-center justify-center">
      <EyeAnimation />
    </div>
  );
}

export default App;