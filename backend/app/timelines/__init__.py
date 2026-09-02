"""Timeline documents (ADR-0002): OTIO-inspired, versioned, diffable JSON.

The canonical edit format. Concepts mirror OpenTimelineIO — Timeline →
Tracks → Clips with source in/out points and record positions — but the
storage format is plain JSON so documents stay diffable and the client
needs no OTIO library. Cutlass-specific metadata (reason, confidence)
rides on clips; OTIO adapters at the export boundary (Plan 3).
"""
