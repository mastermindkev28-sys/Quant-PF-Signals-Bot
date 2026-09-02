# TradingView indicators

## H1 Range → Break → CHoCH → IFVG

`h1_range_break_choch_ifvg.pine` — Pine Script v6, overlay indicator.

It marks the high and low of the H1 candle that opens after **05:30 PST**, then labels the
three-step reversal sequence that follows.

### Install

1. TradingView → **Pine Editor** → *Open* → *New indicator*.
2. Paste the contents of `h1_range_break_choch_ifvg.pine`.
3. **Save**, then **Add to chart**.

Run it on a chart at or below the range length — 1m, 5m or 15m give the cleanest
break / CHoCH / IFVG detection. On a 1H chart the range is a single candle and the
structure logic has very little to work with.

### What it draws

| Element | Meaning |
| --- | --- |
| Shaded box | The H1 candle itself (06:00–07:00 PST by default) |
| Green / red rays | The range high and low, extended right until the next day's window |
| Dotted ray | Range midpoint (EQ) |
| `BREAK ▲` / `BREAK ▼` | First close (or wick, if configured) beyond the range high / low |
| `CHoCH ▲` / `CHoCH ▼` | Market structure flipped — a close through the last opposing swing |
| `IFVG` box | A fair value gap price closed through, now acting as opposite-side S/R |
| `SETUP ▲` / `SETUP ▼` | Break → opposing CHoCH → IFVG, in that order |

### The timing

`05:30 PST` is 08:30 ET — the US data release. The first hourly candle that *opens*
after it is **06:00 PST**, which is the default (`Range opens at 06:00`, length 60m).

Some futures feeds print hourly candles aligned to `:30`. If yours does, set
**Range opens at** to `05:30` and you get the 05:30–06:30 candle instead.

The timezone input is IANA (`America/Los_Angeles`), so PST/PDT is handled for you —
the range tracks 06:00 local through the DST switch rather than drifting an hour.

### The logic

**Range.** Every bar whose open time falls inside the window extends the running high /
low. When the window closes the levels freeze and the day's state machine arms.

**Break.** The first close beyond the high or low. Uncheck *Require a candle close* to
count a wick through instead. The break sets the direction the setup expects to fade:
break the high → the model waits for a bearish CHoCH.

**CHoCH.** Swings come from `ta.pivothigh` / `ta.pivotlow` with `Swing pivot length`
bars either side (default 5, so a pivot confirms 5 bars late). A close through the last
unbroken swing high flips structure bullish; through the last swing low, bearish. It's a
**CHoCH** when that flip reverses the prior direction and a **BOS** when it continues it —
BOS labels are off by default. Only the CHoCH that opposes the break advances the setup.

**IFVG.** A three-candle imbalance — `low > high[2]` (bullish) or `high < low[2]`
(bearish). When price *closes* fully through a gap, the gap inverts: a bullish FVG closed
below becomes bearish resistance, a bearish FVG closed above becomes bullish support.
That inversion is the IFVG, and it's what the boxes and `IFVG` labels mark. An IFVG is
deleted once price closes back through its far side.

**Setup.** `SETUP` fires only when the IFVG direction matches the CHoCH direction and both
followed the range break. Turn off *Setup label requires Break → CHoCH → IFVG* to label
every IFVG independently.

### Alerts

Eight `alertcondition` entries — range high / low broken, CHoCH up / down, bullish /
bearish IFVG, and long / short setup — plus dynamic `alert()` messages carrying the ticker
on the two setup conditions. Add them from the chart's alert dialog with this indicator as
the condition source.

### Tuning notes

- **Swing pivot length** is the main knob. 3–5 on 1m/5m, 8–10 on 15m and up. Larger means
  fewer, later, more meaningful CHoCH labels.
- **Min FVG size (ticks)** filters out noise gaps on fast instruments. On NQ, 4–8 ticks
  cuts most of them.
- **Drop FVGs older than N bars** keeps the chart clean when you scroll back — 0 keeps
  everything the 500-box limit allows.
- **Keep previous days** off deletes yesterday's range so only the current one is drawn.
