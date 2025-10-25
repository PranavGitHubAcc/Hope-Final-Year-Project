import React, { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Heart, Activity, Battery, User, Calendar, MapPin, AlertCircle, FileText, Download, Eye, X } from 'lucide-react';

export default function App() {
  const [vitals, setVitals] = useState({ heart_rate: 0, spo2: 0, battery: 0, status: 'disconnected' });
  const [patient, setPatient] = useState(null);
  const [hrHistory, setHrHistory] = useState([]);
  const [spo2History, setSpo2History] = useState([]);
  const [showDocument, setShowDocument] = useState(false);
  const [pdfFile, setPdfFile] = useState(null);

  // Handle file upload
  const handleFileUpload = (event) => {
    const file = event.target.files[0];
    if (file && file.type === 'application/pdf') {
      const fileUrl = URL.createObjectURL(file);
      setPdfFile(fileUrl);
    }
  };

  useEffect(() => {
    fetch('http://localhost:5000/api/patient')
      .then(res => res.json())
      .then(data => setPatient(data))
      .catch(err => console.error(err));

    fetch('http://localhost:5000/api/vitals/history')
      .then(res => res.json())
      .then(data => {
        if (data.heart_rate && data.heart_rate.length > 0) {
          setHrHistory(data.heart_rate.slice(-30).map((item) => ({
            time: new Date(item.timestamp).toLocaleTimeString(),
            value: item.value
          })));
        }
        if (data.spo2 && data.spo2.length > 0) {
          setSpo2History(data.spo2.slice(-30).map((item) => ({
            time: new Date(item.timestamp).toLocaleTimeString(),
            value: item.value
          })));
        }
      })
      .catch(err => console.error(err));

    const ws = new WebSocket('ws://localhost:5000/ws');
    
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setVitals(data);
    };

    const fetchHistory = () => {
      fetch('http://localhost:5000/api/vitals/history')
        .then(res => res.json())
        .then(data => {
          if (data.heart_rate && data.heart_rate.length > 0) {
            setHrHistory(data.heart_rate.slice(-30).map((item) => ({
              time: new Date(item.timestamp).toLocaleTimeString(),
              value: item.value
            })));
          }
          if (data.spo2 && data.spo2.length > 0) {
            setSpo2History(data.spo2.slice(-30).map((item) => ({
              time: new Date(item.timestamp).toLocaleTimeString(),
              value: item.value
            })));
          }
        })
        .catch(err => console.error(err));
    };

    const interval = setInterval(fetchHistory, 10000);

    return () => {
      ws.close();
      clearInterval(interval);
    };
  }, []);

  const getStatusColor = () => vitals.status === 'connected' ? 'bg-emerald-500' : 'bg-rose-500';
  const getHRStatus = () => {
    if (vitals.heart_rate > 100) return 'text-rose-600';
    if (vitals.heart_rate < 60) return 'text-amber-600';
    return 'text-emerald-600';
  };
  const getSPO2Status = () => vitals.spo2 < 95 ? 'text-rose-600' : 'text-emerald-600';

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50 p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-3xl font-bold text-slate-800 tracking-tight">Patient Monitoring</h1>
            <p className="text-slate-500 text-sm mt-1">Real-time vital signs dashboard</p>
          </div>
          <div className="flex items-center gap-3 bg-white px-4 py-2 rounded-xl shadow-sm">
            <div className={`w-2.5 h-2.5 rounded-full ${getStatusColor()} animate-pulse`}></div>
            <span className="text-sm font-medium text-slate-700 capitalize">{vitals.status}</span>
          </div>
        </div>

        {/* Patient Info Card */}
        {patient && (
          <div className="bg-white rounded-2xl shadow-lg p-6 mb-6 border border-slate-100">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-4">
                <div className="w-16 h-16 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-2xl flex items-center justify-center shadow-lg">
                  <User className="w-8 h-8 text-white" />
                </div>
                <div>
                  <h2 className="text-2xl font-bold text-slate-800">{patient.name}</h2>
                  <p className="text-slate-600 mt-0.5">{patient.condition}</p>
                </div>
              </div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6 pt-6 border-t border-slate-100">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-slate-100 rounded-lg flex items-center justify-center">
                  <Calendar className="w-5 h-5 text-slate-600" />
                </div>
                <div>
                  <p className="text-xs text-slate-500 font-medium">Age</p>
                  <p className="font-semibold text-slate-800">{patient.age} years</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-slate-100 rounded-lg flex items-center justify-center">
                  <User className="w-5 h-5 text-slate-600" />
                </div>
                <div>
                  <p className="text-xs text-slate-500 font-medium">Gender</p>
                  <p className="font-semibold text-slate-800">{patient.gender}</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-slate-100 rounded-lg flex items-center justify-center">
                  <MapPin className="w-5 h-5 text-slate-600" />
                </div>
                <div>
                  <p className="text-xs text-slate-500 font-medium">Room</p>
                  <p className="font-semibold text-slate-800">{patient.room}</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-slate-100 rounded-lg flex items-center justify-center">
                  <Calendar className="w-5 h-5 text-slate-600" />
                </div>
                <div>
                  <p className="text-xs text-slate-500 font-medium">Admitted</p>
                  <p className="font-semibold text-slate-800">{patient.admitted}</p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Vitals Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-white rounded-2xl shadow-lg p-5 border border-slate-100">
            <div className="flex items-center justify-between mb-3">
              <div className="w-12 h-12 bg-gradient-to-br from-rose-500 to-pink-600 rounded-xl flex items-center justify-center shadow-lg">
                <Heart className="w-6 h-6 text-white" />
              </div>
              <span className="text-xs font-semibold text-slate-400">BPM</span>
            </div>
            <p className="text-sm text-slate-500 font-medium mb-1">Heart Rate</p>
            <p className={`text-3xl font-bold ${getHRStatus()}`}>{vitals.heart_rate}</p>
            {(vitals.heart_rate > 100 || vitals.heart_rate < 60) && vitals.heart_rate > 0 && (
              <div className="flex items-center gap-2 text-xs text-amber-700 bg-amber-50 px-2 py-1.5 rounded-lg mt-3">
                <AlertCircle className="w-3.5 h-3.5" />
                <span className="font-medium">Abnormal</span>
              </div>
            )}
          </div>

          <div className="bg-white rounded-2xl shadow-lg p-5 border border-slate-100">
            <div className="flex items-center justify-between mb-3">
              <div className="w-12 h-12 bg-gradient-to-br from-blue-500 to-cyan-600 rounded-xl flex items-center justify-center shadow-lg">
                <Activity className="w-6 h-6 text-white" />
              </div>
              <span className="text-xs font-semibold text-slate-400">%</span>
            </div>
            <p className="text-sm text-slate-500 font-medium mb-1">Oxygen Saturation</p>
            <p className={`text-3xl font-bold ${getSPO2Status()}`}>{vitals.spo2}</p>
            {vitals.spo2 < 95 && vitals.spo2 > 0 && (
              <div className="flex items-center gap-2 text-xs text-rose-700 bg-rose-50 px-2 py-1.5 rounded-lg mt-3">
                <AlertCircle className="w-3.5 h-3.5" />
                <span className="font-medium">Low Level</span>
              </div>
            )}
          </div>

          <div className="bg-white rounded-2xl shadow-lg p-5 border border-slate-100">
            <div className="flex items-center justify-between mb-3">
              <div className="w-12 h-12 bg-gradient-to-br from-emerald-500 to-teal-600 rounded-xl flex items-center justify-center shadow-lg">
                <Battery className="w-6 h-6 text-white" />
              </div>
              <span className="text-xs font-semibold text-slate-400">%</span>
            </div>
            <p className="text-sm text-slate-500 font-medium mb-1">Device Battery</p>
            <p className="text-3xl font-bold text-slate-800">{vitals.battery}</p>
          </div>

          <div className="bg-gradient-to-br from-indigo-500 to-purple-600 rounded-2xl shadow-lg p-5 border border-indigo-200">
            <div className="flex items-center justify-between mb-3">
              <div className="w-12 h-12 bg-white/20 backdrop-blur rounded-xl flex items-center justify-center">
                <FileText className="w-6 h-6 text-white" />
              </div>
            </div>
            <p className="text-sm text-indigo-100 font-medium mb-1">Patient Records</p>
            <p className="text-xl font-bold text-white mb-3">Medical File</p>
            {pdfFile ? (
              <button
                onClick={() => setShowDocument(true)}
                className="w-full bg-white/20 hover:bg-white/30 backdrop-blur text-white text-sm font-medium py-2 px-3 rounded-lg transition-all duration-200 flex items-center justify-center gap-2"
              >
                <Eye className="w-4 h-4" />
                View Document
              </button>
            ) : (
              <label className="w-full bg-white/20 hover:bg-white/30 backdrop-blur text-white text-sm font-medium py-2 px-3 rounded-lg transition-all duration-200 flex items-center justify-center gap-2 cursor-pointer">
                <FileText className="w-4 h-4" />
                Upload PDF
                <input
                  type="file"
                  accept="application/pdf"
                  onChange={handleFileUpload}
                  className="hidden"
                />
              </label>
            )}
          </div>
        </div>

        {/* Charts */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-white rounded-2xl shadow-lg p-6 border border-slate-100">
            <h3 className="text-lg font-bold text-slate-800 mb-4 flex items-center gap-2">
              <div className="w-1 h-6 bg-gradient-to-b from-rose-500 to-pink-600 rounded-full"></div>
              Heart Rate Trend
            </h3>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={hrHistory}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="time" stroke="#94a3b8" style={{ fontSize: '12px' }} />
                <YAxis stroke="#94a3b8" domain={[40, 120]} style={{ fontSize: '12px' }} />
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: 'white', 
                    border: '1px solid #e2e8f0',
                    borderRadius: '8px',
                    fontSize: '12px'
                  }} 
                />
                <Line type="monotone" dataKey="value" stroke="#f43f5e" strokeWidth={2.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white rounded-2xl shadow-lg p-6 border border-slate-100">
            <h3 className="text-lg font-bold text-slate-800 mb-4 flex items-center gap-2">
              <div className="w-1 h-6 bg-gradient-to-b from-blue-500 to-cyan-600 rounded-full"></div>
              SpO2 Trend
            </h3>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={spo2History}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="time" stroke="#94a3b8" style={{ fontSize: '12px' }} />
                <YAxis stroke="#94a3b8" domain={[85, 100]} style={{ fontSize: '12px' }} />
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: 'white', 
                    border: '1px solid #e2e8f0',
                    borderRadius: '8px',
                    fontSize: '12px'
                  }} 
                />
                <Line type="monotone" dataKey="value" stroke="#3b82f6" strokeWidth={2.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Document Modal */}
        {showDocument && (
          <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-5xl h-[90vh] flex flex-col">
              <div className="flex items-center justify-between p-4 border-b border-slate-200">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-lg flex items-center justify-center">
                    <FileText className="w-5 h-5 text-white" />
                  </div>
                  <div>
                    <h3 className="font-bold text-slate-800">Patient Medical Record</h3>
                    <p className="text-xs text-slate-500">John Doe - Medical File</p>
                  </div>
                </div>
                <button
                  onClick={() => setShowDocument(false)}
                  className="w-10 h-10 hover:bg-slate-100 rounded-lg flex items-center justify-center transition-colors"
                >
                  <X className="w-5 h-5 text-slate-600" />
                </button>
              </div>
              <div className="flex-1 overflow-hidden bg-slate-50">
                {pdfFile ? (
                  <iframe
                    src={pdfFile}
                    className="w-full h-full border-0"
                    title="Patient Document"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center">
                    <p className="text-slate-500">No document uploaded</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}