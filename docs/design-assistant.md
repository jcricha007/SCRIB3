# Design workspace and local Ollama

The **Design** tab provides paper layout, Grid/Spiral/Rosette patterns with adjustable detail, 90-degree rotation, horizontal/vertical mirrors, one-step design undo, and SVG export. Changes immediately update the paper preview. Undo covers source changes such as imports, patterns, transformations, and applying an AI proposal; it does not undo machine settings or paper-layout inputs. SVG export preserves the fitted paper geometry in physical millimeters regardless of display units. Re-import still follows SCRIB3's normal artwork-bounds fitting behavior.

## Start Ollama

Open your installed Ollama application. If using the CLI installation without a running server, run `ollama serve` in a separate Terminal. `ollama list` shows installed models.

In SCRIB3 choose **Design → Open Ollama assistant → Refresh models**. Select an installed local model. The app connects to `127.0.0.1:11434`; proxies and redirects are disabled. Cloud tags and model records with remote-host/model metadata are excluded. Each generation rechecks that the selected model is installed locally. The app does not download models or require a cloud API key. **Save choice** saves the selected model together with the current machine preset.

## Chat and make a drawing

- **Chat** streams the model's answer and supports follow-up messages. The request contains a bounded recent conversation and a summary of the current design/paper/pen settings. It does not include files, the connection log, or live controller coordinates. Replies are displayed as text; they cannot execute code, write GRBL settings, move the machine, or apply art.
- **Use prompt as design brief** copies your chat input to **Create / revise**. **Create new drawing** requests new line art. **Revise workspace drawing** supplies the current source geometry with the requested changes.
- A successful response appears in the assistant's preview. **Use drawing in workspace** applies it. Existing work remains unchanged while the model runs, and **Undo design** restores the previous source after applying a proposal.
- **New conversation** clears chat context. Conversation history and un-applied previews are session-only. Export SVG to keep a design.

AI drawings use validated polylines with at most 60 strokes and 120 points per stroke. Revision rejects more complex source geometry instead of silently dropping detail. Generated coordinates must be finite and inside the normalized drawing area; malformed, empty, oversized, or incomplete responses are rejected. Artwork still needs visual review, calibration, and normal G-code review before plotting.

## Errors and cancellation

The assistant reports an unavailable server, no installed local models, model errors, malformed replies, and timeouts within its window. Chat and generation run on a worker thread so the desktop and plotter controls remain responsive. One assistant request runs at a time. **Cancel request** discards results and stops accepting streamed text; the local request may take time to return or reach its network timeout. Closing the assistant hides it and cancels the pending result. Reopening reuses the window.

Chat retains at most 12 recent messages and sends up to 24,000 characters of recent content; individual prompts are limited to 8,000 characters. Drawing briefs are limited to 12,000 characters and revision geometry to 20,000 serialized characters. This is a local conversational/design assistant, not autonomous machine control.

References: [installed models](https://docs.ollama.com/api/tags), [chat API](https://docs.ollama.com/api/chat), [streaming](https://docs.ollama.com/api/streaming), [structured outputs](https://docs.ollama.com/capabilities/structured-outputs).
