// CONSTELLATION — the library of the mind
const Constellation = () => {
  const stars = React.useMemo(() => {
    const arr = [];
    for (let i = 0; i < 220; i++) {
      arr.push({
        left: Math.random() * 100,
        top: Math.random() * 100,
        size: Math.random() > 0.95 ? 'bright' : '',
        color: Math.random() > 0.92 ? ['amber','teal','rose'][Math.floor(Math.random()*3)] : '',
        blink: Math.random() * 4,
      });
    }
    return arr;
  }, []);

  const motifs = [
    { x: 22, y: 34, label: 'waiting', color: 'amber', count: 47 },
    { x: 52, y: 22, label: 'the ficus', color: 'teal', count: 12 },
    { x: 68, y: 42, label: 'rugs / classed objects', color: 'teal', count: 8 },
    { x: 38, y: 58, label: 'tennis academy', color: 'amber', count: 23 },
    { x: 74, y: 68, label: 'addiction', color: 'rose', count: 34 },
    { x: 20, y: 72, label: 'the prorector', color: 'amber', count: 6 },
    { x: 48, y: 78, label: 'hal watching', color: 'teal', count: 19 },
  ];

  // connections
  const lines = [
    [0,1],[1,2],[0,3],[3,6],[3,4],[5,0],[6,2]
  ];

  return (
    <div className="stage fade-in" style={{ overflow: 'hidden' }}>
      <div style={{
        position: 'absolute', inset: 0,
        background: 'radial-gradient(ellipse at center, rgba(20,15,30,0.4) 0%, var(--room) 80%)',
      }}/>
      {stars.map((s, i) => (
        <div key={i} className={`star ${s.size} ${s.color}`} style={{
          left: s.left + '%', top: s.top + '%',
          animation: `twinkle ${3 + s.blink}s ease-in-out infinite`,
          animationDelay: s.blink + 's',
        }}/>
      ))}
      <style>{`@keyframes twinkle { 0%,100% { opacity: 0.4; } 50% { opacity: 1; } }`}</style>

      {/* motif lines */}
      <svg style={{ position: 'absolute', inset: 0 }} preserveAspectRatio="none" viewBox="0 0 100 100">
        {lines.map(([a,b], i) => (
          <line key={i}
            x1={motifs[a].x} y1={motifs[a].y}
            x2={motifs[b].x} y2={motifs[b].y}
            stroke="rgba(200,134,31,0.22)" strokeWidth="0.08"/>
        ))}
      </svg>

      {/* motif nodes */}
      {motifs.map((m, i) => (
        <div key={i} style={{
          position: 'absolute',
          left: m.x + '%', top: m.y + '%',
          transform: 'translate(-50%, -50%)',
          textAlign: 'center',
        }}>
          <div style={{
            width: 8 + m.count/4, height: 8 + m.count/4,
            borderRadius: '50%',
            background: `var(--${m.color})`,
            boxShadow: `0 0 ${14 + m.count/2}px var(--${m.color})`,
            margin: '0 auto 8px',
          }}/>
          <div style={{
            fontFamily: 'Literata, serif', fontStyle: 'italic',
            fontSize: 13, color: 'rgba(245,235,210,0.85)',
            letterSpacing: '-0.005em',
          }}>
            {m.label}
          </div>
          <div style={{
            fontFamily: 'JetBrains Mono, monospace', fontSize: 9,
            letterSpacing: '0.18em', textTransform: 'uppercase',
            color: 'rgba(245,235,210,0.35)', marginTop: 2,
          }}>
            {m.count} mentions · {i%2?'carried':'unresolved'}
          </div>
        </div>
      ))}

      {/* title */}
      <div style={{
        position: 'absolute', top: 80, left: 0, right: 0,
        textAlign: 'center',
        color: 'rgba(245,235,210,0.85)',
      }}>
        <div className="label" style={{ color: 'rgba(245,235,210,0.4)' }}>
          constellation · infinite jest · 23 sessions · 4.1 weeks
        </div>
        <h2 style={{
          fontFamily: 'Literata, serif', fontSize: 28, fontWeight: 500,
          marginTop: 10, letterSpacing: '-0.01em',
          color: 'rgba(250,240,220,0.95)',
        }}>
          The sky of your reading life.
        </h2>
      </div>

      {/* scale */}
      <div style={{
        position: 'absolute', bottom: 64, left: '50%', transform: 'translateX(-50%)',
        display: 'flex', gap: 28, alignItems: 'center',
        fontFamily: 'JetBrains Mono, monospace', fontSize: 10,
        letterSpacing: '0.18em', textTransform: 'uppercase',
        color: 'rgba(245,235,210,0.55)',
      }}>
        <div><span style={{ color: 'var(--amber)' }}>◉</span> Sam · patterns</div>
        <div><span style={{ color: 'var(--teal)' }}>◉</span> Ellis · craft</div>
        <div><span style={{ color: 'var(--rose)' }}>◉</span> Kit · tensions</div>
      </div>
    </div>
  );
};

window.Constellation = Constellation;
