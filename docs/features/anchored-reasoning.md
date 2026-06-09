# Anchored Reasoning

Status: **Reference**
Date: 2026-05-09
Tier: Premium · Patent-pending

---

## What it is

**Anchored reasoning is the premium tier of Agience that anchors every
AI answer to verified evidence in your encrypted memory and signals an
explicit gap when the evidence doesn't warrant a conclusion.**

In plain language: it's the layer that stops your AI from making
things up.

The platform-tier of Agience gives your AI an encrypted, source-attributed
substrate to work with — that's the data layer. Anchored reasoning
(patent-pending) extends those guarantees into the AI's answer surface
itself.

---

## What it does

When an MCP-capable agent (Claude Desktop, VS Code, Cursor, your own)
queries Agience with Anchored reasoning enabled:

1. The query routes to encrypted hybrid search across the principal's
   authorized light-cone — the same encryption guarantees as the
   platform tier apply.
2. The reasoning engine selects evidence anchors from the returned
   artifacts using a constrained-attention mechanism that operates on
   evidence density rather than retrieval similarity alone.
3. Generation is conditioned on retrieved, provenance-tagged anchors at
   every step. An impasse signal fires when the registry of available
   evidence does not warrant continuation.
4. The returned answer carries source attribution per claim and an
   explicit gap when evidence is insufficient or contradictory.

---

## What it prevents

**Hallucination.** Generation is anchored to retrieved evidence at
every step, not just at the input prompt. The model cannot wander into
invented territory because the gate fires before it produces tokens
the evidence does not support.

**Confident wrong answers.** When evidence is partial or contradictory,
the system surfaces the gap explicitly rather than producing a smooth
but wrong synthesis.

**Untraceable claims.** Every claim in an Anchored answer points back
to the artifact that produced it. The provenance chain is preserved at
the answer level, not just at the artifact level.

---

## When to use it

Anchored reasoning is the right tier when:

- Your AI agents operate on data where being wrong has a cost
  (regulated content, customer commitments, compliance evidence, legal
  research, medical context).
- You need traceable answers — every claim in an AI output must
  resolve to a source artifact that a human can review.
- Your team has been burned by an AI hallucination before. The premium
  upgrade lands the moment the first wrong AI summary causes pain.
- You're deploying AI on regulated data and need both encryption (the
  platform tier) and answer-level provenance (Anchored reasoning).

It's overkill when:

- You're prototyping; the open-source platform tier is the right
  starting point.
- The cost of a hallucinated answer is low (creative writing,
  brainstorming, ideation).
- Your AI agents only need the encrypted memory layer, not
  answer-level reasoning over it.

---

## How it works with the rest of the platform

Anchored reasoning depends on the platform's three structural
properties:

**Encrypted hybrid search.** The reasoning runs against your encrypted
substrate; we never see your content or queries. (Same encryption
guarantees as the platform tier.)

**Built-in provenance.** Anchored reasoning needs evidence-attributed
artifacts to anchor against. Workspace artifacts that have crossed the
commit boundary into a Collection are the canonical evidence base.

**MCP-native interface.** Anchored reasoning is exposed through the
same MCP tool surface as the platform's regular search. Any
MCP-capable agent can opt in.

---

## What you'll see in your AI client

With Anchored reasoning enabled, AI answers come back with two things
the platform tier doesn't provide:

1. **Per-claim source attribution.** Each statement in the answer
   points to the artifact (or specific evidence span within an
   artifact) that produced it. Click through; see exactly where the
   claim came from.
2. **Explicit-gap signaling.** When the evidence doesn't warrant a
   conclusion, the answer says so. You'll see phrases like *"the
   committed evidence does not include information about X"* rather
   than a confident fabrication.

---

## Pricing

Anchored reasoning is included in the **Anchored** tier:

- **Anchored** — $199 / seat / month
- Includes everything in Team
- Adds: Anchored reasoning, source-linked answer provenance,
  explicit-gap signaling, dedicated key management, priority SLA,
  single-tenant available

For pricing details, see [Pricing](https://agience.ai/pricing).
For Enterprise (custom integrations, dedicated infrastructure,
on-prem), [contact us](https://agience.ai/contact).

---

## Patent posture

The Anchored reasoning mechanism is **patent-pending**. Specifically,
the constrained-attention layer with evidence-density selection and
explicit-gap signaling is the subject of an in-progress patent
application. The encryption substrate the reasoning runs on is
patent-pending separately.

---

## Self-host availability

Anchored reasoning is available for hosted, single-tenant, and
self-host deployments under the Anchored tier or Enterprise license.
The same code that runs the hosted product runs in your environment —
no feature gating between deployment postures.

---

## Frequently asked questions

**Is Anchored reasoning a separate product?**
No. It's a tier of Agience. You buy Agience; you upgrade to Anchored
when you need the answer-level guarantees. One brand, one product,
one upgrade path.

**Will it work with Claude / VS Code / Cursor?**
Yes. Anything that speaks MCP. The reasoning runs server-side on
Agience; your client just makes regular MCP tool calls.

**Does Anchored reasoning train on my data?**
No. The encryption guarantees of the platform tier still apply —
storage gets ciphertext; we never see your data. The reasoning
mechanism operates against your authorized light-cone of encrypted
artifacts.

**What happens to claims with insufficient evidence?**
They surface as explicit gaps in the answer. You'll see a statement
like *"the committed evidence does not warrant a conclusion about X"*
instead of a fabricated answer.

**How is this different from RAG?**
RAG retrieves from a (typically plaintext) index and injects retrieved
chunks into a prompt. Anchored reasoning retrieves from an encrypted
index *and* constrains generation to retrieved evidence at every step.
Different mechanisms, different guarantees, different patent posture.

**Can I get Anchored reasoning without the encryption layer?**
No. Anchored reasoning depends on the platform's encrypted substrate
and provenance model. The two are designed together; the upgrade ladder
is Free → Pro → Team → Anchored.

---

## See also

- [Platform overview](../overview/platform-overview.md)
- [What is Agience?](../overview/what-is-agience.md)
- [Security model](../architecture/security-model.md)
- [Pricing](https://agience.ai/pricing)
- [Architecture white paper](../../.dev/vision/architecture-white-paper.md)
  (internal — public PDF on request)
