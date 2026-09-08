import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { ProviderConnections } from "@/components/provider-connections";

export default function SettingsPage() {
  return (
    <div className="reading-settings">
      <Link href="/#library" className="text-link"><ArrowLeft size={15} /> Back to your library</Link>
      <p className="quiet-eyebrow">Make yourself at home</p>
      <h1>Settings & connections</h1>
      <p>Connect the services you use for reading conversations and voice.</p>
      <ProviderConnections />
      <Link className="text-link" href="/after-dark">Explore After Dark</Link>
    </div>
  );
}
