import { useState, useRef } from 'react';
import * as speechsdk from 'microsoft-cognitiveservices-speech-sdk';

function App() {
  const [isRecording, setIsRecording] = useState(false);
  const [audioUrl, setAudioUrl] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [apiResponse, setApiResponse] = useState('');
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [transcription, setTranscription] = useState('');
  
  const mediaRecorder = useRef(null);
  const streamRef = useRef(null);
  const synthesizerRef = useRef(null);
  const audioPlayerRef = useRef(null);
  
  // Configuration - Update API endpoint to match Python server
  const API_URL = 'http://localhost:8000/process_audio'; // Updated to Python server
  const USER_ID = 'user1';
  const SESSION_ID = '4533361482989043712';

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

      const SPEECH_KEY = 'Dlh8qsFb9znouchcwXCMiWDkItfpkHHS3vdGK4TG0Kaxw4EeGVPWJQQJ99BJACgEuAYXJ3w3AAAYACOGI9OI';
      const SPEECH_REGION = 'italynorth';
      
      const speechConfig = speechsdk.SpeechConfig.fromSubscription(
        SPEECH_KEY, 
        SPEECH_REGION
      );
      
      speechConfig.speechSynthesisVoiceName = "en-US-AvaNeural";
      
      const audioPlayer = new speechsdk.SpeakerAudioDestination();
      audioPlayerRef.current = audioPlayer;
      const audioConfig = speechsdk.AudioConfig.fromSpeakerOutput(audioPlayer);
      
      const synthesizer = new speechsdk.SpeechSynthesizer(speechConfig, audioConfig);
      synthesizerRef.current = synthesizer;
      
      console.log('Starting Azure TTS for:', text);
      
      synthesizer.speakTextAsync(
        text,
        (result) => {
          if (result.reason === speechsdk.ResultReason.SynthesizingAudioCompleted) {
            console.log('Azure TTS completed successfully!');
          } else if (result.reason === speechsdk.ResultReason.Canceled) {
            console.error('Azure TTS cancelled:', result.errorDetails);
          }
          
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
        audio: { 
          echoCancellation: true, 
          noiseSuppression: true,
          sampleRate: 16000 // Better for speech recognition
        } 
      });
      
      streamRef.current = stream;
      
      // Use WAV format for better compatibility with speech recognition
      const options = { mimeType: 'audio/webm;codecs=opus' };
      const recorder = new MediaRecorder(stream, options);
      mediaRecorder.current = recorder;
      
      const chunks = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunks.push(event.data);
      };

      recorder.onstop = async () => {
        const audioBlob = new Blob(chunks, { type: 'audio/webm' });
        setAudioUrl(URL.createObjectURL(audioBlob));
        setIsRecording(false);
        
        await sendAudioToApi(audioBlob);
        
        if (streamRef.current) {
          streamRef.current.getTracks().forEach(track => track.stop());
        }
      };

      recorder.start();
      setIsRecording(true);
      console.log('Recording started...');
    } catch (err) {
      console.error('Microphone error:', err);
      alert('Could not access microphone');
    }
  };

  const stopRecording = () => {
    if (mediaRecorder.current?.state === 'recording') {
      mediaRecorder.current.stop();
      console.log('Recording stopped');
    }
  };

  const sendAudioToApi = async (audioBlob) => {
    setIsProcessing(true);
    setApiResponse('');
    setTranscription('');
    
    try {
      const formData = new FormData();
      formData.append('file', audioBlob, 'recording.webm');
      formData.append('user_id', USER_ID);
      formData.append('session_id', SESSION_ID);
      
      console.log('Sending audio to API...');
      
      const response = await fetch(API_URL, {
        method: 'POST',
        body: formData,
      });
      
      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`API error: ${response.status} - ${errorText}`);
      }
      
      const data = await response.json();
      console.log('API Response:', data);
      
      setTranscription(data.transcription);
      setApiResponse(data.response);
      
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
          
          @keyframes listening-left {
            0%, 100% { transform: translateX(0px) scale(1); }
            50% { transform: translateX(-8px) scale(1.05); }
          }
          
          @keyframes listening-right {
            0%, 100% { transform: translateX(0px) scale(1); }
            50% { transform: translateX(8px) scale(1.05); }
          }
          
          @keyframes speaking {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.1); }
          }
          
          @keyframes thinking {
            0%, 100% { opacity: 0.8; }
            50% { opacity: 1; }
          }
          
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
    <div className="min-h-screen bg-black flex flex-col items-center justify-center p-4">
      <EyeAnimation />
      
      {/* Status Display */}
      <div className="text-white text-center mb-4">
        {isRecording && <p className="text-cyan-400">🎤 Recording... Click eye to stop</p>}
        {isProcessing && <p className="text-yellow-400">⚡ Processing audio...</p>}
        {isSpeaking && <p className="text-green-400">🔊 Speaking...</p>}
      </div>
      
      {/* Response Display */}
      {(transcription || apiResponse) && (
        <div className="bg-gray-900 rounded-lg p-6 max-w-2xl w-full mt-4">
          {transcription && (
            <div className="mb-4">
              <h3 className="text-cyan-400 font-bold mb-2">You said:</h3>
              <p className="text-white">{transcription}</p>
            </div>
          )}
          {apiResponse && (
            <div>
              <h3 className="text-green-400 font-bold mb-2">Hope AI:</h3>
              <p className="text-white">{apiResponse}</p>
            </div>
          )}
        </div>
      )}
      
      {/* Controls */}
      <div className="mt-6 flex space-x-4">
        <button
          onClick={stopSpeaking}
          disabled={!isSpeaking}
          className={`px-4 py-2 rounded ${
            isSpeaking 
              ? 'bg-red-600 hover:bg-red-700 text-white' 
              : 'bg-gray-600 text-gray-400 cursor-not-allowed'
          }`}
        >
          Stop Speaking
        </button>
        
        {audioUrl && (
          <button
            onClick={() => window.open(audioUrl, '_blank')}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded"
          >
            Play Recording
          </button>
        )}
      </div>
    </div>
  );
}

export default App;