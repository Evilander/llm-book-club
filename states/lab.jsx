// LAB — close-reading instrument
const Lab = ({ onClose, cursorMode, setCursorMode }) => {
  const [notes, setNotes] = useState([
    { id: 1, t: '20:14', text: 'the ficus = the book’s whole method', color: 'amber' },
    { id: 2, t: '20:18', text: 'lowercase persian → class signal', color: 'teal' },
    { id: 3, t: '20:22', text: 'disagree with kit. the gag earns it.', color: 'rose' },
  ]);

  return (
    <div style={{
      position: 'fixed', right: 0, top: 0, bottom: 0,
      width: 'min(520px, 45vw)',
      background: 'rgba(15,11,9,0.96)',
      borderLeft: '1px solid rgba(245,235,210,0.1)',
      padding: 36,
      zIndex: 40,
      animation: 'slide-in-right 450ms var(--spring-paper)',
      backdropFilter: 'blur(20px)',
      color: 'rgba(245,235,210,0.88)',
      display: 'flex', flexDirection: 'column',
    }}>
      <style>{`@keyframes slide-in-right { from { transform: translateX(100%);} to { transform: translateX(0);} }`}</style>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 28 }}>
        <div>
          <div className="label" style={{ color: 'rgba(245,235,210,0.45)' }}>lab · marginalia</div>
          <h3 style={{
            fontFamily: 'Literata, serif', fontSize: 22, fontWeight: 500,
            marginTop: 6, color: 'rgba(250,240,220,0.95)',
          }}>The Waiting Room</h3>
        </div>
        <button onClick={onClose} style={{
          background: 'transparent', border: 'none',
          color: 'rgba(245,235,210,0.6)', cursor: 'pointer',
          fontFamily: 'JetBrains Mono, monospace', fontSize: 11,
          letterSpacing: '0.2em',
        }}>close ✕</button>
      </div>

      {/* cursor mode switcher */}
      <div className="label" style={{ color: 'rgba(245,235,210,0.45)', marginBottom: 10 }}>
        instrument
      </div>
      <div style={{ display: 'flex', gap: 4, marginBottom: 28 }}>
        {[
          ['reader', 'reading',  '⟨ ⟩'],
          ['finger', 'annotate', '👆'],
          ['loupe',  'evidence', '⊕'],
          ['quill',  'note',     '✎'],
        ].map(([m, lab, ico]) => (
          <button key={m} onClick={() => setCursorMode(m)} style={{
            flex: 1,
            background: cursorMode === m ? 'rgba(200,134,31,0.18)' : 'rgba(245,235,210,0.04)',
            border: `1px solid ${cursorMode === m ? 'var(--amber)' : 'rgba(245,235,210,0.1)'}`,
            color: cursorMode === m ? 'rgba(250,240,220,0.95)' : 'rgba(245,235,210,0.7)',
            padding: '10px 6px',
            borderRadius: 2,
            fontFamily: 'JetBrains Mono, monospace', fontSize: 10,
            letterSpacing: '0.14em', textTransform: 'uppercase',
            cursor: 'pointer',
          }}>
            <div style={{ fontSize: 14, marginBottom: 4 }}>{ico}</div>
            {lab}
          </button>
        ))}
      </div>

      {/* scrubber — your own thinking across sessions */}
      <div className="label" style={{ color: 'rgba(245,235,210,0.45)', marginBottom: 10 }}>
        your thinking · 4 sessions
      </div>
      <div style={{
        background: 'rgba(245,235,210,0.04)',
        border: '1px solid rgba(245,235,210,0.1)',
        borderRadius: 2,
        padding: 14,
        marginBottom: 24,
      }}>
        <input type="range" min="0" max="3" step="1" defaultValue="3"
          style={{ width: '100%', accentColor: 'var(--amber)' }}/>
        <div style={{
          display: 'flex', justifyContent: 'space-between',
          fontFamily: 'JetBrains Mono, monospace', fontSize: 9,
          color: 'rgba(245,235,210,0.5)', letterSpacing: '0.14em',
          textTransform: 'uppercase', marginTop: 8,
        }}>
          <span>apr 2</span>
          <span>apr 8</span>
          <span>apr 14</span>
          <span style={{ color: 'var(--amber)' }}>tonight</span>
        </div>
      </div>

      {/* notes */}
      <div className="label" style={{ color: 'rgba(245,235,210,0.45)', marginBottom: 12 }}>
        your marks
      </div>
      <div style={{ flex: 1, overflowY: 'auto', paddingRight: 8 }}>
        {notes.map(n => (
          <div key={n.id} style={{
            padding: '12px 0 12px 16px',
            borderLeft: `1px solid var(--${n.color})`,
            marginBottom: 10,
          }}>
            <div style={{
              fontFamily: 'JetBrains Mono, monospace', fontSize: 10,
              letterSpacing: '0.18em', color: 'rgba(245,235,210,0.4)',
              marginBottom: 4,
            }}>
              {n.t}
            </div>
            <div style={{
              fontFamily: 'Literata, serif', fontStyle: 'italic',
              fontSize: 14, lineHeight: 1.5,
              color: 'rgba(245,235,210,0.85)',
            }}>
              {n.text}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

window.Lab = Lab;
