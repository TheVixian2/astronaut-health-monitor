# Live demo script

**Setup on one Mac:** backend running, watchOS Simulator open, browser with
Self-check and Ground side by side.

**Mission setting:** Mars. `one_way_delay_s` compressed to **20 s** for the demo.
Label it on screen — `Mars · 22 min one-way (demo: 20 s)`. Time compression is
normal in mission simulation; stating it openly reads as rigour, hiding it does
not.

## The run (about 90 seconds)

1. **Open on the Self-check view.** Nominal. Point out that every number is shown
   against *this astronaut's own* baseline, not a population average.
2. **Press "Simulate exertion" on the watch.** Heart rate ramps.
3. **`orthostatic` fires.** Self-check lights up **instantly**:
   *"Act on board now — 10 min window"* plus the protocol line.
   The watch shows the condition name, severity colour, a haptic, and the single
   pre-written action line.
4. **Point at the Ground panel.** It shows `incoming — 00:18`, counting down.
   The flight surgeon does not know yet.
5. **Let it land.** Eighteen seconds later the alert appears on Ground.
6. **The line:** *"On a real Mars mission that gap is 22 minutes, not 18 seconds.
   Her window to act was 10. That's why the decision has to be made on board."*
7. **Then SANS** — slow-onset, so the delay genuinely doesn't matter. Same system,
   opposite verdict: *"Ground will advise."*

## Why this order

The countdown is what does the work. Judges don't need to sit through 22 minutes
of silence — they need to see that one screen knows and the other doesn't yet,
and watch a clock. Two conditions with opposite verdicts proves the software is
making a judgement, not just alarming.

## Rehearse

- Run it end to end at least twice before judging. `--seed-baseline` and the
  fixed random seed mean it plays the same every time.
- Have `POST /debug/scenario` ready as a fallback if the watch misbehaves.
