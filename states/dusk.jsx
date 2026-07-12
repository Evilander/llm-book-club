// DUSK — the room reading to itself
const Dusk = ({ onEnter }) => {
  const [time, setTime] = React.useState(new Date());
  React.useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 30000);
    return () => clearInterval(id);
  }, []);

  const hh = time.getHours().toString().padStart(2, '0');
  const mm = time.getMinutes().toString().padStart(2, '0');

  const motes = React.useMemo(() =>
    Array.from({ length: 18 }, (_, i) => ({
      left: Math.random() * 100,
      top: 60 + Math.random() * 40,
      delay: Math.random() * 20,
      dur: 18 + Math.random() * 8,
    })), []);

  return (
    <div className="stage fade-in">
      {/* motes */}
      {motes.map((m, i) => (
        <div key={i} className="mote" style={{
          left: m.left + '%', top: m.top + '%',
          animationDelay: m.delay + 's',
          animationDuration: m.dur + 's',
        }} />
      ))}

      {/* the book at rest, distant */}
      <div className="book" style={{
        width: '560px', height: '340px',
        transform: 'perspective(1800px) rotateX(52deg) translateY(60px) scale(0.8)',
        filter: 'brightness(0.55) blur(0.6px)',
        opacity: 0.85,
      }}>
        <div className="book-half verso">
          <div className="page-content" style={{ padding: '40px 30px', opacity: 0.3 }}>
            <div style={{
              fontFamily: 'Literata, serif', fontSize: '10px',
              lineHeight: 1.9, color: 'var(--ink-mute)',
            }}>
              {Array.from({length: 12}).map((_,i) => (
                <div key={i} style={{
                  width: (70 + Math.random()*28) + '%',
                  height: 6, background: 'var(--ink-mute)',
                  opacity: 0.35, marginBottom: 6, borderRadius: 1,
                }}/>
              ))}
            </div>
          </div>
        </div>
        <div className="gutter" />
        <div className="book-half recto">
          <div className="page-content" style={{ padding: '40px 30px', opacity: 0.3 }}>
            {Array.from({length: 12}).map((_,i) => (
              <div key={i} style={{
                width: (66 + Math.random()*30) + '%',
                height: 6, background: 'var(--ink-mute)',
                opacity: 0.35, marginBottom: 6, borderRadius: 1,
              }}/>
            ))}
          </div>
        </div>
      </div>

      {/* overlay: the invitation */}
      <div style={{
        position: 'absolute',
        top: '50%', left: '50%',
        transform: 'translate(-50%, -50%) translateY(140px)',
        textAlign: 'center',
        color: 'rgba(245,235,210,0.88)',
        maxWidth: 520,
      }}>
        <div className="label" style={{ color: 'rgba(245,235,210,0.45)', marginBottom: 14 }}>
          {hh}:{mm} · the room is open
        </div>
        <h1 style={{
          fontFamily: 'Literata, serif',
          fontSize: 38, fontWeight: 500,
          lineHeight: 1.15, letterSpacing: '-0.01em',
          color: 'rgba(250,240,220,0.95)',
          marginBottom: 18,
        }}>
          Already reading<br/>
          <em style={{ color: 'var(--amber)', fontWeight: 400 }}>to itself.</em>
        </h1>
        <p style={{
          fontFamily: 'Literata, serif', fontStyle: 'italic',
          fontSize: 15, lineHeight: 1.65,
          color: 'rgba(245,235,210,0.55)',
          marginBottom: 32,
        }}>
          Sam was in the middle of something about time.
          Ellis pulled a line from p.&nbsp;214. Kit, predictably, disagreed.
        </p>
        <button
          onClick={onEnter}
          style={{
            background: 'transparent',
            border: '1px solid rgba(200,134,31,0.5)',
            color: 'rgba(250,240,220,0.95)',
            padding: '14px 28px',
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: 11, letterSpacing: '0.2em', textTransform: 'uppercase',
            cursor: 'pointer',
            borderRadius: 2,
            transition: 'all 300ms ease',
          }}
          onMouseEnter={e => {
            e.target.style.background = 'rgba(200,134,31,0.12)';
            e.target.style.borderColor = 'var(--amber)';
          }}
          onMouseLeave={e => {
            e.target.style.background = 'transparent';
            e.target.style.borderColor = 'rgba(200,134,31,0.5)';
          }}
        >
          Step in
        </button>
      </div>

      <div className="whisper-strip">
        {[0,1,2,3,4,5,6].map(i => (
          <div key={i} className="dot" style={{ animationDelay: (i*0.2) + 's' }}/>
        ))}
        <div className="label" style={{ marginLeft: 12, color: 'rgba(245,235,210,0.3)', fontSize: 9 }}>
          ambient · last session’s whisper
        </div>
      </div>
    </div>
  );
};

window.Dusk = Dusk;
