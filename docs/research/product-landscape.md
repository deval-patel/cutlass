# Product Landscape Research (Sept 2026)

Research underpinning Cutlass's positioning. Sources cited inline; all claims checked against vendor pages or credible coverage. Companion doc: [`editing-style-techniques.md`](editing-style-techniques.md).

## The one-line summary

Everything that does real "AI rough cut" is closed-source cloud SaaS metered by credits; everything that is local or open stops at silence removal or subtitles. **No product combines self-hosted processing + multimodal rough-cut generation + a built-in editor.**

## Tier-by-tier landscape

### Transcript-driven / text-based editors
- **Descript** — category-defining text-based editor (transcript edits drive the timeline), Studio Sound, filler-word removal, "Underlord" AI assistant. Cloud SaaS; killed all legacy plans Nov 2025 and restructured pricing around media minutes + AI credits, triggering sustained user backlash ([pricing](https://www.descript.com/pricing), [Trustpilot](https://www.trustpilot.com/review/descript.com), [r/podcasting](https://www.reddit.com/r/podcasting/comments/1oc0zo3/latest_descript_changes/)). Best for talking-head/podcast; not timeline-heavy finishing.
- **Gling** — desktop AI editor for YouTubers: transcribe → AI removes bad takes/silences/filler → refine → export FCPXML/XML to FCP/Premiere/Resolve or direct MP4+SRT ([gling.ai](https://www.gling.ai/)). Decisions are transcript-analysis-driven; reviews note it's tuned for talking-head content.
- **Wisecut** — web auto-editor: silence removal, captions, auto-reframe, music ducking; ~$23–83/mo, cloud only ([pricing](https://wisecut.ai/pricing)).

### Long-video-to-shorts clippers
- **Opus Clip** — long video → 20+ shorts with a 0–99 "Virality Score" (hooks/pacing/topic shifts; methodology unpublished), auto-reframe, AI captions, brand *cosmetics* ([virality score](https://help.opus.pro/docs/article/virality-score), [brand templates](https://www.opus.pro/brand-templates)). The dominant user complaint: selection quality — "you didn't use the good part," and reviewing AI output can take longer than editing manually ([r/podcasting](https://www.reddit.com/r/podcasting/comments/1ud8hlw/anyone_else_spending_more_time_reviewing_ai_clips/)).
- **Vizard**, **Klap** — same category, similar mechanics and complaints ([vizard.ai](https://vizard.ai/), [klap.app/pricing](https://klap.app/pricing)).

### Local/desktop single-purpose automators
- **Timebolt** — local silence/jump-cut app, .01s cut control, filler-word removal, punch-ins, "BYO Model" hook; exports Premiere/Resolve/FCP XML/FCPXML. Closed source despite being local ([timebolt.io](https://timebolt.io/)).
- **Recut** — silence removal, $129 one-time, exports timelines to your NLE ([getrecut.com](https://getrecut.com/)).
- **auto-editor** (open source) — free CLI loudness-based silence cutting; the community's free Recut alternative ([GitHub](https://github.com/WyattBlue/auto-editor)).

### NLE plugins and pro NLEs
- **AutoPod** ($29/mo, Premiere): multi-cam speaker cutting, jump cuts, social clips ([autopod.fm](https://www.autopod.fm/)). **Firecut** ($8–21/mo): silence removal, take trimming, AI captions/zooms for Premiere + Resolve ([firecut.ai](https://firecut.ai/)).
- **Premiere Pro** — AI Media Intelligence (natural-language semantic search over footage), text-based editing, Generative Extend, Firefly "Creative Agent" orchestrating multi-step workflows; all cloud-account tied ([Adobe blog](https://blog.adobe.com/en/publish/2026/04/15/adobe-extends-leadership-video-unleashing-new-ai-powered-creation-firefly-reinventing-color-editors-in-premiere), [Puget Systems explainer](https://www.pugetsystems.com/blog/2025/02/27/premiere-pro-media-intelligence-what-it-is/)).
- **DaVinci Resolve free** — extremely capable editor, but Neural Engine AI features + text-based editing are Studio-only ($295) ([Toolfarm comparison](https://www.toolfarm.com/tutorial/in-depth-davinci-resolve-studio-vs-the-free-version/)).
- **CapCut** — free tier gutted in 2025; ToS granted ByteDance perpetual irrevocable content licenses; BIPA lawsuit; F privacy grade ([The Record](https://therecord.media/capcut-privacy-lawsuit-illinois-bipa-bytedance-china), [VerifyWise](https://verifywise.ai/ai-trust-index/capcut)). Strongest exodus pressure among desktop creators.

### 2024–2026 "AI rough cut" entrants (the real competitive signal)
- **Eddie AI** — "assistant video editor for pros" / "Cursor for video": chat-driven rough cuts, stringouts, multicam sync; exports Premiere/FCP/Resolve/**Avid EDL/OTIO**; pay-as-you-go credits (~500 credits/hour of source) ([heyeddie.ai](https://www.heyeddie.ai/), [pricing](https://www.heyeddie.ai/pricing)). Built on LLMs (Claude/GPT-class) as the brains.
- **Kino** — AI-native collaborative editor "for people and agents"; adjustable agent autonomy; "Search by Meaning" over footage/transcripts/visuals ([kino.ai](https://kino.ai/), [breakdown](https://mayalekhi.substack.com/p/startup-breakdown-kino-ai)).
- **Threadline Studio** — documentary/narrative workspace; multi-hour recordings; **prosodic (intonation) analysis** drives assembly; XML export ([CineD](https://www.cined.com/threadline-launches-ai-editing-workspace-with-intonation-analysis-and-native-xml-export-to-premiere-resolve-and-final-cut-pro/)).
- **Mosaic** (YC) — "frontier video agents": agentic editing with A/B-tested variants from the same footage ([mosaic.so](https://mosaic.so/)).

### Open-source editors
- **Kdenlive** — the most AI-capable OSS editor: Whisper speech-to-text subtitles, AI object segmentation, proxy editing. No rough-cut generation, no LLM features ([docs](https://docs.kdenlive.org/en/effects_and_filters/speech_to_text.html)).
- **Shotcut/OpenShot** — usable but crash-prone on longer projects, no AI ([r/software](https://www.reddit.com/r/software/comments/1ag2qhf/kdenlive_vs_shotcut_vs_openshot/)). **OLIVE** — stalled/alpha.
- **Timeline Studio** — Tauri/Rust/Next.js AI editor, Ollama support, headless render; MIT **with Commons Clause** (not fully free commercially), alpha ([GitHub](https://github.com/chatman-media/timeline-studio)).

## Documented pain we can attack

1. **Travel/action creators with hours of non-talking-head footage.** Highly-edited travel vlogs take 15–30 hours each ([Gling blog](https://www.gling.ai/blog/how-long-does-it-really-take-to-edit-a-youtube-video)); every transcript-first tool under-serves footage whose value is *visual*, not spoken.
2. **Privacy distrust.** CapCut ToS/BIPA; Descript pricing/trust backlash; active demand for local/offline pipelines in r/selfhosted, r/LocalLLaMA, r/privacy; pro-market validation via Axle AI's on-prem MAM business.
3. **Unexplained selection.** The loudest clippers complaint is "you didn't use the good part" with no per-cut reasoning. Explainability is a trust feature nobody offers.
4. **Credit metering resentment.** Per-hour credits (Eddie ~500/hr; Descript's 2025 restructure) vs. flat local cost.
5. **Free/OSS editor users have no AI path** — Kdenlive stops at subtitles; Resolve free gates all AI behind Studio.

## Ranked differentiators for Cutlass

1. Only self-hostable end-to-end AI rough-cut pipeline (privacy + flat cost).
2. Multimodal selection for non-talking-head footage — the travel/action niche.
3. Built-in lightweight editor closing the rough-cut → finished-cut loop locally.
4. **Prompt-controllable editorial style** — no product exposes editorial style parameters (target shot-length distribution, cut density, J/L offsets); everyone's "templates" are cosmetic branding. Open, defensible space, grounded in film statistics (see companion doc).
5. Explainable edit decisions (per-segment reasons/scores surfaced in UI).
6. Open interchange (OTIO/EDL/FCPXML) — upgrades the entire OSS editor ecosystem.
7. Windows-first desktop experience (many AI-native entrants are Mac-centric).
8. Scriptable/batch (watch-folder, headless API) for automation users.
