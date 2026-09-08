"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowDown, ArrowRight, BookOpen, MessageCircle, Users } from "lucide-react";
import { BookShelf } from "@/components/book-shelf";

export default function Home() {
  const router = useRouter();

  return (
    <div className="reading-home">
      <section className="welcome" aria-labelledby="welcome-title">
        <p className="quiet-eyebrow">Reading, in good company</p>
        <h1 id="welcome-title">A good book.<br />A little <em>company.</em></h1>
        <p className="welcome-copy">A quiet place to read, wonder, and talk it through.<br className="desktop-break" /> With an AI companion who stays close to the page.</p>
        <a className="reading-button" href="#library">Find your next page <ArrowRight size={17} aria-hidden="true" /></a>
        <div className="page-study" aria-hidden="true">
          <div className="page-study-left"><span>I</span><i /><i /><i /><i /><i /></div>
          <div className="page-study-right"><i /><i /><i className="marked-line" /><i /><i /></div>
          <div className="margin-note"><span className="companion-dot" /> Shall we stay with this passage?</div>
        </div>
        <a href="#how-it-feels" className="welcome-footnote">Your pace. Your questions. A little more from every page. <ArrowDown size={13} aria-hidden="true" /></a>
      </section>

      <div className="home-library" id="library">
        <BookShelf onSelectBook={(bookId) => router.push(`/books/${bookId}/read`)} />
      </div>

      <section className="reading-ways" id="how-it-feels" aria-labelledby="reading-ways-title">
        <p className="quiet-eyebrow">Room for your kind of reading</p>
        <h2 id="reading-ways-title">Follow the sentence.<br /><em>See where it takes you.</em></h2>
        <div className="reading-ways-grid">
          <div><BookOpen size={21} strokeWidth={1.4} aria-hidden="true" /><h3>Just you and the book</h3><p>A clear page, comfortable type, and your place kept for next time. Take as long as you like.</p></div>
          <div><MessageCircle size={21} strokeWidth={1.4} aria-hidden="true" /><h3>A thought in the margin</h3><p>Pause at a sentence. Ask a question. Your AI reading companion is right beside the text.</p></div>
          <div><Users size={21} strokeWidth={1.4} aria-hidden="true" /><h3>Bring it to the book club</h3><p>Choose a chapter and hear a few different perspectives. A conversation you can always bring back to the book.</p></div>
        </div>
      </section>
      <footer className="reading-footer"><span>ReadAgain. A little closer to the book.</span><div><Link href="/after-dark">After Dark</Link><Link href="/settings">Settings & connections</Link></div></footer>
    </div>
  );
}
