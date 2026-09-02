You are editing a video of total duration ${duration}s. Below are per-frame
notes from the whole video (timestamp, description, label)${transcript_intro}.
Produce the FIRST DRAFT CUT: select contiguous keep-segments containing the
meaningful content while cutting dead air, filler, intros/outros, and
repetition.

${style_block}

Output ONLY a JSON array of keep-segments:
[{"start_s": <float>, "end_s": <float>, "reason": "<why kept>", "confidence": <0-1>}]

Rules: segments must be chronological and non-overlapping, cover at most the
video duration, keep the video coherent, and pad boundaries slightly.
${transcript_block}
Notes:
$notes
