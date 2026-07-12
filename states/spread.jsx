// SPREAD — the core. discussion in the margins.
const { useState, useEffect, useRef } = React;

const SLICE_TEXT = [
  { t: "You are, at the age of eleven, sitting in what is technically a waiting room, though the room does not know it is waiting.", tag: "p1" },
  { t: "A ficus in the corner has given up on the idea of autumn and decided, privately, to continue.", tag: "p2", footnote: 1 },
  { t: "Mario is drawing hexagons. Hal is not drawing anything. Hal is watching the ficus.", tag: "p3" },
  { t: "Across the rug — which is the rug your mother has called persian without ever quite committing to the lowercase — the prorector is on the phone.", tag: "p4", lift: true },
  { t: "“No,” he says. “No. Yes. That's the one. That's the specific one.”", tag: "p5" },
  { t: "The rug is not, in fact, Persian. It is from a store in Allston that sells the idea of Persian rugs.", tag: "p6", footnote: 2, unstable: true },
  { t: "Later, much later, Hal will remember this afternoon as the one in which nothing happened, which is exactly the kind of afternoon that is doing all of the happening.", tag: "p7" },
];

const MARGINALIA = [
  {
    role: 'sam', agent: 'Sam', col: 'left', top: 60,
    text: <>The opening joke is gentle: a <em>waiting room that does not know it is waiting</em>. Wallace is training us — this room is everything this book is about.</>,
    thread: 'p1',
  },
  {
    role: 'ellis', agent: 'Ellis', col: 'right', top: 40,
    gloss: true,
    text: <>The <span style={{color: 'var(--teal)'}}>persian → Persian → not Persian</span> chain collapses capitalisation, authenticity, and maternal authority in eleven words. Cf. the footnote on bus routes.</>,
    thread: 'p4',
    quote: "the rug your mother has called persian without ever quite committing to the lowercase",
    quoteCite: 'exact',
  },
  {
    role: 'kit', agent: 'Kit', col: 'right', top: 240,
    text: <>Counter: the "store in Allston" line is cited in every undergraduate essay and I think we should stop treating it as profound. It's a cheap gag.<sup className="fn-mark">†</sup></>,
    thread: 'p6',
  },
  {
    role: 'sam', agent: 'Sam', col: 'left', top: 300,
    text: <>Ellis — I want you to sit with the ficus for a second. What is <em>giving up on autumn</em> actually doing for us on page one?</>,
  },
];

const Spread = ({ afterDark, skin, density }) => {
  const [activeAgent, setActiveAgent] = useState('ellis');
  const [liftedLine, setLiftedLine] = useState(null);
  const [expandedFn, setExpandedFn] = useState(null);
  const [cursorMode, setCursorMode] = useState('reader');

  // auto-rotate the "speaking" agent
  useEffect(() => {
    const seq = ['sam', 'ellis', 'kit', 'ellis'];
    let i = 0;
    const id = setInterval(() => {
      i = (i + 1) % seq.length;
      setActiveAgent(seq[i]);
      if (seq[i] === 'ellis') setLiftedLine('p4');
      else setLiftedLine(null);
    }, 5200);
    return () => clearInterval(id);
  }, []);

  const bookRef = useRef(null);

  // typographic skin per-book
  const skinCfg = {
    footnote:   { bodyFS: 15, lh: 1.85, tracking: '-0.005em', marginFS: 13, ff: '"Literata", serif' },
    noir:       { bodyFS: 14.5, lh: 1.7, tracking: '0.008em', marginFS: 12.5, ff: '"Literata", serif' },
    poetry:     { bodyFS: 17, lh: 2.2, tracking: '-0.002em', marginFS: 14, ff: '"Literata", serif' },
  }[skin] || { bodyFS: 15.5, lh: 1.85, tracking: '-0.005em', marginFS: 13, ff: '"Literata", serif' };

  const dense = density === 'expert';

  return (
    <div className="stage fade-in">
      <div className="book" ref={bookRef} style={afterDark ? { filter: 'brightness(0.98)' } : {}}>
        {/* VERSO — the slice */}
        <div className="book-half verso">
          <div className="page-content" style={{
            fontFamily: skinCfg.ff,
            padding: dense ? '52px 44px 60px 180px' : '64px 56px 72px 180px',
          }}>
            <div className="label" style={{
              color: 'var(--ink-mute)', marginBottom: 8,
            }}>
              Volume I · Chapter 3 · pp. 172–173
            </div>
            <h3 style={{
              fontFamily: 'Literata, serif',
              fontSize: 20, fontWeight: 600,
              color: 'var(--ink)',
              marginBottom: 20,
              letterSpacing: '-0.01em',
            }}>
              The Waiting Room
            </h3>

            <div style={{
              fontSize: skinCfg.bodyFS,
              lineHeight: skinCfg.lh,
              letterSpacing: skinCfg.tracking,
              color: 'var(--ink)',
              columnGap: 24,
            }}>
              {SLICE_TEXT.map((p, i) => {
                const isLifted = liftedLine === p.tag && p.lift;
                const marg = MARGINALIA.find(m => m.thread === p.tag);
                return (
                  <p key={p.tag} style={{
                    marginBottom: 14,
                    position: 'relative',
                  }}>
                    {/* inline quote extraction by Ellis */}
                    {p.lift ? (
                      <>
                        {"Across the rug — which is the rug "}
                        <span className={`lift ${isLifted ? 'lifted' : ''}`}>
                          your mother has called persian without ever quite committing to the lowercase
                        </span>
                        {" — the prorector is on the phone."}
                      </>
                    ) : p.unstable ? (
                      <>
                        The rug is not, in fact, Persian. It is from <span className="unstable-ink">a store in Allston that sells the idea of Persian rugs</span>.
                      </>
                    ) : p.tag === 'p2' ? (
                      <>A ficus in the corner has given up on the idea of autumn and decided, privately, to continue.<sup className="fn-mark" onClick={() => setExpandedFn(expandedFn === 1 ? null : 1)}>1</sup></>
                    ) : p.tag === 'p6' ? (
                      <>The rug is not, in fact, Persian. It is from <span className="unstable-ink">a store in Allston that sells the idea of Persian rugs</span>.<sup className="fn-mark" onClick={() => setExpandedFn(expandedFn === 2 ? null : 2)}>2</sup></>
                    ) : p.t}
                  </p>
                );
              })}
            </div>

            {/* footnote expansion */}
            {expandedFn && (
              <div style={{
                marginTop: 'auto', paddingTop: 20,
                borderTop: '1px solid var(--ink-faint)',
                fontFamily: 'Literata, serif',
                fontSize: 12, lineHeight: 1.6,
                color: 'var(--ink-mute)', fontStyle: 'italic',
              }}>
                <sup style={{ color: 'var(--rose)', fontWeight: 600 }}>{expandedFn}</sup>{'  '}
                {expandedFn === 1
                  ? <>Ellis: the ficus line is a pocket ars poetica — <span className="cite-exact">decided, privately, to continue</span> describes the novel’s entire method. (Exact.)</>
                  : <>Kit: this gag doesn’t earn its length. The sentence is proud of itself. <span className="cite-fuzzy">store in Allston</span>, fuzzy match, but the reading stands.</>
                }
              </div>
            )}
          </div>
        </div>

        <div className="gutter"/>

        {/* RECTO — the illuminated margin */}
        <div className="book-half recto">
          <div className="page-content" style={{ padding: dense ? '52px 44px 60px' : '64px 56px 72px', position: 'relative' }}>
            <div className="label" style={{ color: 'var(--ink-mute)', marginBottom: 8 }}>
              the room · live
            </div>
            <h3 style={{
              fontFamily: 'Literata, serif', fontSize: 15,
              fontStyle: 'italic', color: 'var(--ink-soft)',
              marginBottom: 28, fontWeight: 400,
            }}>
              three voices, reading with you
            </h3>

            {MARGINALIA.filter(m => m.col === 'right').map((m, i) => (
              <MarginTurn key={i} m={m} active={activeAgent === m.role} />
            ))}

            {/* the quote Ellis lifted, arriving here */}
            {liftedLine === 'p4' && (
              <div style={{
                marginTop: 32,
                padding: '12px 0 12px 20px',
                borderLeft: '1px solid var(--teal)',
                fontFamily: 'Literata, serif',
                fontStyle: 'italic',
                fontSize: 14,
                lineHeight: 1.6,
                color: 'var(--ink-soft)',
                animation: 'fade-in 600ms ease',
              }}>
                <span className="cite-exact">“your mother has called persian without ever quite committing to the lowercase”</span>
                <div style={{
                  fontStyle: 'normal', fontSize: 10,
                  letterSpacing: '0.18em', textTransform: 'uppercase',
                  color: 'var(--teal)', marginTop: 8,
                  fontFamily: 'JetBrains Mono, monospace',
                }}>
                  ellis · exact · p. 172
                </div>
              </div>
            )}

            {/* user's own hand */}
            <div style={{
              marginTop: 'auto',
              paddingTop: 24,
              fontFamily: 'Literata, serif',
              fontStyle: 'italic', fontSize: 13,
              color: 'var(--blue)',
              borderTop: '1px dashed var(--ink-faint)',
            }}>
              <div className="label" style={{ color: 'var(--blue)', marginBottom: 6 }}>
                your hand
              </div>
              <p>— but the ficus is doing the same thing the prorector’s phone call is doing. why isn’t anyone calling that out?</p>
            </div>

            {/* Sam's aura — bottom left of recto */}
            <div className={`aura sam ${activeAgent === 'sam' ? 'active' : ''}`}
              style={{ width: 180, height: 180, bottom: -40, left: -60 }}/>
            <div className={`aura ellis ${activeAgent === 'ellis' ? 'active' : ''}`}
              style={{ width: 140, height: 140, top: 20, right: -50 }}/>
            <div className={`aura kit ${activeAgent === 'kit' ? 'active' : ''}`}
              style={{ width: 120, height: 120, bottom: 120, right: -40 }}/>
          </div>
        </div>

        {/* LEFT marginalia — Sam speaks from the verso's inner left rail */}
        <div style={{
          position: 'absolute',
          left: 20, top: 72, bottom: 72,
          width: 140,
          display: 'flex', flexDirection: 'column',
          gap: 24,
          pointerEvents: 'none',
        }}>
          {MARGINALIA.filter(m => m.col === 'left').map((m, i) => (
            <div key={i} style={{
              marginTop: i === 0 ? 40 : 140,
              opacity: activeAgent === m.role ? 1 : 0.38,
              transition: 'opacity 800ms ease',
              fontSize: 11.5, lineHeight: 1.55,
            }}>
              <div className={`margin-band ${m.role}`} style={{ paddingLeft: 12, fontSize: 11.5, lineHeight: 1.5 }}>
                <div className={`agent-tag ${m.role}`} style={{ fontSize: 8.5 }}>
                  <span style={{
                    width: 4, height: 4, borderRadius: '50%',
                    background: m.role === 'sam' ? 'var(--amber)' : m.role === 'kit' ? 'var(--rose)' : 'var(--teal)',
                    boxShadow: activeAgent === m.role ? `0 0 8px currentColor` : 'none',
                  }}/>
                  {m.agent}
                </div>
                {m.text}
              </div>
            </div>
          ))}
        </div>

        {/* thread line — SVG from verso quote to Ellis */}
        {liftedLine === 'p4' && (
          <svg className="thread-svg" viewBox="0 0 1000 600" preserveAspectRatio="none">
            <path className="thread-path"
              d="M 340 280 C 450 260, 600 240, 720 200"
              stroke="var(--teal)"
            />
          </svg>
        )}

        {/* latency-as-aura: slow breathing left margin if waiting */}
      </div>

      {/* session timeline — slim rail at bottom */}
      <div style={{
        position: 'fixed', bottom: 24, left: '50%',
        transform: 'translateX(-50%)',
        display: 'flex', alignItems: 'center', gap: 16,
        padding: '10px 20px',
        background: 'rgba(12,10,9,0.6)',
        border: '1px solid rgba(255,255,255,0.08)',
        borderRadius: 100,
        fontFamily: 'JetBrains Mono, monospace', fontSize: 10,
        letterSpacing: '0.15em', textTransform: 'uppercase',
        color: 'rgba(245,235,210,0.6)',
        backdropFilter: 'blur(14px)',
      }}>
        <span style={{ color: activeAgent === 'sam' ? 'var(--amber)' : activeAgent === 'ellis' ? 'var(--teal)' : 'var(--rose)' }}>
          ◉ {activeAgent}
        </span>
        <span style={{ opacity: 0.5 }}>·</span>
        <span>p. 172–173</span>
        <span style={{ opacity: 0.5 }}>·</span>
        <span>24:16</span>
        <span style={{ opacity: 0.5 }}>·</span>
        <span style={{ color: 'var(--teal)' }}>◉ 4 citations · 3 exact</span>
      </div>
    </div>
  );
};

const MarginTurn = ({ m, active }) => {
  return (
    <div style={{
      marginBottom: 28,
      opacity: active ? 1 : 0.38,
      transition: 'opacity 900ms ease',
    }}>
      {m.gloss ? (
        <div className={`margin-band ${m.role}`}>
          <div className={`agent-tag ${m.role}`}>
            <span style={{
              width: 5, height: 5, borderRadius: '50%',
              background: m.role === 'ellis' ? 'var(--teal)' : m.role === 'kit' ? 'var(--rose)' : 'var(--amber)',
              boxShadow: active ? `0 0 10px currentColor` : 'none',
            }}/>
            {m.agent} · interlinear gloss
          </div>
          {m.text}
        </div>
      ) : (
        <div className={`margin-band ${m.role}`}>
          <div className={`agent-tag ${m.role}`}>
            <span style={{
              width: 5, height: 5, borderRadius: '50%',
              background: m.role === 'kit' ? 'var(--rose)' : m.role === 'sam' ? 'var(--amber)' : 'var(--teal)',
              boxShadow: active ? `0 0 10px currentColor` : 'none',
            }}/>
            {m.agent}{m.role === 'kit' ? ' · footnote' : ''}
          </div>
          {m.text}
        </div>
      )}
    </div>
  );
};

window.Spread = Spread;
