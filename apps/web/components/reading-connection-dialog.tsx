"use client";

import { useRef } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { ProviderConnections } from "./provider-connections";

export function ReadingConnectionDialog({ open, onOpenChange, onReady }: { open: boolean; onOpenChange: (open: boolean) => void; onReady: () => void }) {
  const opener = useRef<HTMLElement | null>(null);
  return <Dialog.Root open={open} onOpenChange={onOpenChange}>
    <Dialog.Portal>
      <Dialog.Overlay className="reading-dialog-scrim connection-dialog-scrim" />
      <Dialog.Content className="reading-connection-dialog" onOpenAutoFocus={() => { opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null; }} onCloseAutoFocus={event => { event.preventDefault(); if (opener.current?.isConnected) opener.current.focus(); }}>
        <div className="preferences-heading"><Dialog.Title>A partner beside the page</Dialog.Title><Dialog.Close aria-label="Close connection settings"><X size={19} /></Dialog.Close></div>
        <Dialog.Description className="connection-dialog-intro">Connect once, then return to your book. Your place and anything you’re writing stay here.</Dialog.Description>
        <ProviderConnections onReady={() => { onOpenChange(false); onReady(); }} />
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>;
}
