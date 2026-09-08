/** Deterministic SSE framing regressions, with no browser or model calls. */
import assert from 'node:assert/strict';
import ts from 'typescript';
import { readFile } from 'node:fs/promises';
const source = await readFile(new URL('../lib/event-stream.ts', import.meta.url), 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } }).outputText;
const { readEventStream } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`);
async function decode(parts) {
  const stream = new ReadableStream({ start(controller) { for (const part of parts) controller.enqueue(part); controller.close(); } });
  const events = [];
  for await (const event of readEventStream(stream)) events.push(event);
  return events;
}
const encoder = new TextEncoder();
const text = ': comment\r\nid: one\r\ndata: {"type":"message_delta",\r\ndata: "delta":"Céline 🌿"}\r\n\r\ndata:{"type":"done"}\r\r';
const bytes = encoder.encode(text);
for (let i = 0; i <= bytes.length; i++) assert.deepEqual(await decode([bytes.slice(0, i), bytes.slice(i)]), [{ type: 'message_delta', delta: 'Céline 🌿' }, { type: 'done' }]);
assert.deepEqual(await decode([...bytes].map(byte => Uint8Array.of(byte))), [{ type: 'message_delta', delta: 'Céline 🌿' }, { type: 'done' }]);
assert.deepEqual(await decode([encoder.encode('data: {"type":"done"}\n')]), [], 'incomplete frames are discarded');
await assert.rejects(decode([encoder.encode('data: {broken}\n\n')]), SyntaxError);
await assert.rejects(decode(Array.from({ length: 20 }, () => encoder.encode('data: ' + 'a'.repeat(60000) + '\n'))), /exceeds/);
console.log('PASS: every UTF-8/CRLF split, one-byte frames, multiline data, comments, malformed/truncated events and total frame limit.');
