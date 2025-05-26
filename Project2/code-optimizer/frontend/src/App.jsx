import React, {useEffect, useState} from "react";
import { createSession, cloneRepo, getFile, optimise, checkConnection } from "./api";


export default function App() {
  const [repoURL, setRepoURL] = useState("");
  const [files, setFiles] = useState([]);
  const [selected, setSelected] = useState("");
  const [code, setCode] = useState("");
  const [optimised, setOptimised] = useState("");
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState(false);
  const [connectionOk, setConnectionOk] = useState(true);

  useEffect(() => {
    // Check backend connection on startup
    async function checkBackend() {
      const isConnected = await checkConnection();
      setConnectionOk(isConnected);
      
      if (isConnected) {
        // Create session if connected
        await createSession();
      }
    }
    
    checkBackend();
  }, []);

  const handleClone = async () => {
    setBusy(true);
    try {
      const { files } = await cloneRepo(repoURL);
      setFiles(files);
    } finally {
      setBusy(false);
    }
  };

  const handleSelect = async () => {
    setBusy(true);
    try {
      const txt = await getFile(selected);
      setCode(txt);
    } finally {
      setBusy(false);
    }
  };

  const handleOptimise = async () => {
    setBusy(true);
    try {
      const { optimised } = await optimise(code, feedback);
      setOptimised(optimised);
      setFeedback("");
    } finally {
      setBusy(false);
    }
  };
  if (!connectionOk) {
    return (
      <div style={{ padding: 32, fontFamily: "sans-serif", color: "red" }}>
        <h2>Connection Error</h2>
        <p>Cannot connect to the backend service. Please try again later.</p>
        <button onClick={async () => {
          const isConnected = await checkConnection();
          setConnectionOk(isConnected);
        }}>
          Retry Connection
        </button>
      </div>
    );
  }


  return (
    <div style={{ padding: 32, fontFamily: "sans-serif" }}>
      <h1>Code Optimizer</h1>

      {/* Clone */}
      <input
        placeholder="GitHub URL"
        value={repoURL}
        onChange={(e) => setRepoURL(e.target.value)}
        style={{ width: "60%" }}
      />
      <button onClick={handleClone} disabled={!repoURL || busy}>
        Clone
      </button>

      {/* File select */}
      {files.length > 0 && (
        <>
          <select value={selected} onChange={(e) => setSelected(e.target.value)}>
            <option value="">-- choose file --</option>
            {files.map((f) => (
              <option key={f}>{f}</option>
            ))}
          </select>
          <button onClick={handleSelect} disabled={!selected || busy}>
            Load
          </button>
        </>
      )}

      {/* Editor */}
      {code && (
        <>
          <h3>Source / Feedback</h3>
          <textarea
            rows={15}
            style={{ width: "100%" }}
            value={code}
            onChange={(e) => setCode(e.target.value)}
          ></textarea>

          <input
            placeholder="Add feedback (optional)"
            style={{ width: "100%" }}
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
          />

          <button onClick={handleOptimise} disabled={busy}>
            Optimise
          </button>
        </>
      )}

      {/* Spinner */}
      {busy && <p>⏳ Working…</p>}

      {/* Result */}
      {optimised && (
        <>
          <h3>Optimised</h3>
          <pre>{optimised}</pre>
        </>
      )}
    </div>
  );
}