// SHELF — the physical library
const SHELF_BOOKS = [
  { title: "Infinite Jest",               author: "D. F. Wallace",   color: "#3a5a6a", skin: "footnote",     pages: 1079, pulled: true,  audio: 0.92, last: "Incandenza" },
  { title: "The Left Hand of Darkness",   author: "U. K. Le Guin",   color: "#6a4a3a", skin: "sf-classic",   pages: 304,  pulled: false, audio: 0.71, last: "Estraven" },
  { title: "Bluets",                      author: "M. Nelson",       color: "#3a4a7a", skin: "poetry",       pages: 112,  pulled: false, audio: 0.0,  last: "propositions" },
  { title: "The Long Goodbye",            author: "R. Chandler",     color: "#2a2a2a", skin: "noir",         pages: 379,  pulled: false, audio: 0.88, last: "Marlowe" },
  { title: "Against the Day",             author: "T. Pynchon",      color: "#5a6a3a", skin: "maximalist",   pages: 1085, pulled: false, audio: 0.34, last: "Chums" },
  { title: "The Argonauts",               author: "M. Nelson",       color: "#8a5a6a", skin: "essayistic",   pages: 160,  pulled: false, audio: 0.66, last: "Harry" },
  { title: "Annihilation",                author: "J. VanderMeer",   color: "#3a5a4a", skin: "eerie",        pages: 208,  pulled: false, audio: 0.95, last: "Area X" },
  { title: "Normal People",               author: "S. Rooney",       color: "#7a5a3a", skin: "intimate",     pages: 266,  pulled: false, audio: 0.81, last: "Marianne" },
  { title: "Piranesi",                    author: "S. Clarke",       color: "#4a3a5a", skin: "oneiric",      pages: 272,  pulled: false, audio: 0.79, last: "the House" },
  { title: "Stoner",                      author: "J. Williams",     color: "#5a4a3a", skin: "quiet",        pages: 288,  pulled: false, audio: 0.62, last: "Grace" },
  { title: "Mrs Dalloway",                author: "V. Woolf",        color: "#6a5a7a", skin: "stream",       pages: 194,  pulled: false, audio: 0.74, last: "Clarissa" },
];

const Shelf = ({ onPick }) => {
  const [hover, setHover] = React.useState(null);
  return (
    <div className="stage fade-in">
      <div style={{
        position: 'absolute', top: 90, left: 0, right: 0,
        textAlign: 'center',
      }}>
        <div className="label" style={{ color: 'rgba(245,235,210,0.4)' }}>
          the shelf · 11 volumes · read tonight
        </div>
        <h2 style={{
          fontFamily: 'Literata, serif', fontSize: 28, fontWeight: 500,
          color: 'rgba(250,240,220,0.92)', marginTop: 10,
          letterSpacing: '-0.01em',
        }}>
          What are we opening?
        </h2>
      </div>

      {/* shelf plank */}
      <div style={{
        position: 'absolute',
        bottom: '18%', left: '50%', transform: 'translateX(-50%)',
        width: 'min(92vw, 1280px)',
        height: 340,
        display: 'flex',
        alignItems: 'flex-end',
        justifyContent: 'center',
        gap: 2,
      }}>
        {SHELF_BOOKS.map((b, i) => {
          const isHover = hover === i;
          const pulled = b.pulled;
          const tilt = ((i % 3) - 1) * 1.2;
          return (
            <div
              key={i}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
              onClick={() => onPick(b)}
              style={{
                width: 44 + (b.pages / 80),
                height: pulled ? 290 : 280 - (i % 4) * 6,
                background: `linear-gradient(180deg, ${b.color} 0%, ${b.color}dd 100%)`,
                boxShadow: pulled || isHover
                  ? `0 -10px 30px ${b.color}66, inset 0 0 1px rgba(255,255,255,0.2)`
                  : `inset 0 0 1px rgba(255,255,255,0.15), 0 4px 12px rgba(0,0,0,0.6)`,
                cursor: 'pointer',
                position: 'relative',
                transition: 'transform 500ms var(--spring-paper), height 500ms var(--spring-paper), box-shadow 300ms ease',
                transform: `
                  translateY(${pulled ? -14 : 0}px)
                  translateY(${isHover ? -8 : 0}px)
                  rotate(${tilt}deg)
                `,
                borderRadius: '1px 1px 3px 3px',
                writingMode: 'vertical-rl',
                textOrientation: 'mixed',
                padding: '16px 0',
                color: 'rgba(245,230,200,0.88)',
                fontFamily: 'Literata, serif',
                fontSize: 11,
                fontWeight: 500,
                letterSpacing: '0.04em',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'flex-start',
              }}
            >
              <span style={{ opacity: 0.92 }}>{b.title.toUpperCase()}</span>
              {/* audio-pairing glow on spine */}
              {b.audio > 0.5 && (
                <div style={{
                  position: 'absolute',
                  bottom: 12, left: '50%', transform: 'translateX(-50%)',
                  width: 6, height: 6, borderRadius: '50%',
                  background: 'var(--teal)',
                  boxShadow: `0 0 ${4 + b.audio * 10}px var(--teal)`,
                  opacity: 0.5 + b.audio * 0.5,
                }}/>
              )}
            </div>
          );
        })}
      </div>

      {/* shelf under-plank */}
      <div style={{
        position: 'absolute', bottom: 'calc(18% - 16px)', left: '50%',
        transform: 'translateX(-50%)',
        width: 'min(96vw, 1320px)', height: 16,
        background: 'linear-gradient(180deg, #3a2d1e 0%, #1c1410 100%)',
        boxShadow: '0 14px 30px rgba(0,0,0,0.6)',
      }}/>

      {/* hovered book card */}
      {hover !== null && (
        <div style={{
          position: 'absolute', bottom: '8%', left: '50%',
          transform: 'translateX(-50%)',
          textAlign: 'center',
          color: 'rgba(245,235,210,0.85)',
          fontFamily: 'Literata, serif',
          fontStyle: 'italic',
          fontSize: 14,
          animation: 'fade-in 300ms ease',
        }}>
          <div style={{ fontSize: 17, fontStyle: 'normal', fontWeight: 500, marginBottom: 3 }}>
            {SHELF_BOOKS[hover].title}
          </div>
          <div style={{ color: 'rgba(245,235,210,0.5)', fontSize: 12 }}>
            {SHELF_BOOKS[hover].author} · {SHELF_BOOKS[hover].pages}pp
            {SHELF_BOOKS[hover].audio > 0.5 && <span style={{ color: 'var(--teal)', marginLeft: 10 }}>◉ audiobook · {Math.round(SHELF_BOOKS[hover].audio * 100)}% match</span>}
            {SHELF_BOOKS[hover].pulled && <span style={{ color: 'var(--amber)', marginLeft: 10 }}>← read tonight</span>}
          </div>
        </div>
      )}
    </div>
  );
};

window.Shelf = Shelf;
window.SHELF_BOOKS = SHELF_BOOKS;
