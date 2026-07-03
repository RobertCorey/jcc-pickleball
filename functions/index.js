// Feedback -> GitHub issue bridge.
//
// The site's feedback widget POSTs here (via the Hosting rewrite at
// /api/feedback, so it's same-origin — no CORS needed). This function's only
// job is to turn that into a labeled GitHub issue in RobertCorey/jcc-pickleball,
// so the scheduled growth-loop agent (which reads the repo, not this site's
// backend) can see and act on it via `gh issue list --label feedback` /
// the public issues API.
const { onRequest } = require("firebase-functions/v2/https");
const { defineSecret } = require("firebase-functions/params");

const GITHUB_FEEDBACK_TOKEN = defineSecret("GITHUB_FEEDBACK_TOKEN");
const REPO = "RobertCorey/jcc-pickleball";
const MAX_MESSAGE_LEN = 2000;

exports.submitFeedback = onRequest(
  { secrets: [GITHUB_FEEDBACK_TOKEN], cors: false, maxInstances: 5 },
  async (req, res) => {
    if (req.method !== "POST") {
      res.status(405).json({ ok: false, error: "POST only" });
      return;
    }

    const body = req.body || {};
    // Honeypot: a hidden field real users never fill in; bots that
    // autofill every field will trip it.
    if (typeof body.company === "string" && body.company.trim() !== "") {
      res.status(200).json({ ok: true }); // pretend success, drop silently
      return;
    }

    const message = typeof body.message === "string" ? body.message.trim() : "";
    if (!message) {
      res.status(400).json({ ok: false, error: "message is required" });
      return;
    }
    if (message.length > MAX_MESSAGE_LEN) {
      res.status(400).json({ ok: false, error: "message too long" });
      return;
    }

    const page = typeof body.page === "string" ? body.page.slice(0, 300) : "";
    const email = typeof body.email === "string" ? body.email.trim().slice(0, 200) : "";
    const ua = (req.get("user-agent") || "").slice(0, 300);
    const when = new Date().toISOString();

    const title = `Feedback: ${message.slice(0, 70).replace(/\s+/g, " ")}${message.length > 70 ? "…" : ""}`;
    const bodyLines = [
      message,
      "",
      "---",
      page ? `Page: ${page}` : null,
      email ? `Contact: ${email}` : null,
      `Submitted: ${when}`,
      ua ? `User agent: ${ua}` : null,
    ].filter(Boolean);

    try {
      const ghRes = await fetch(`https://api.github.com/repos/${REPO}/issues`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${GITHUB_FEEDBACK_TOKEN.value()}`,
          Accept: "application/vnd.github+json",
          "Content-Type": "application/json",
          "User-Agent": "openplayri-feedback-function",
        },
        body: JSON.stringify({ title, body: bodyLines.join("\n"), labels: ["feedback"] }),
      });
      if (!ghRes.ok) {
        const detail = await ghRes.text().catch(() => "");
        console.error("GitHub issue creation failed", ghRes.status, detail);
        res.status(502).json({ ok: false, error: "could not file feedback right now" });
        return;
      }
      res.status(200).json({ ok: true });
    } catch (err) {
      console.error("submitFeedback error", err);
      res.status(500).json({ ok: false, error: "unexpected error" });
    }
  }
);
