"""Compiler Probes explainer, version 2: one investigation in five acts, told around the payment service.
Render: VOICE=am_michael manim -r 1920,1080 --fps 30 explainer2.py <Scene>
Every number on screen comes from the result files in ../work4/results or the set 1 machine-code listings."""
import hashlib, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pathlib import Path
from manim import *

HERE = Path(__file__).resolve().parent
R = HERE.parent / 'work4' / 'results'
BG, INK, MUTE, HAIR = '#10131a', '#e9ecf3', '#9aa2b4', '#2c3240'
ACC, GOOD, BAD, WARN = '#8f86ff', '#5fd479', '#ff6b8a', '#f3c85a'
C_JIT, C_AOT, C_GO, C_RUST, C_CS10 = '#eb6834', '#3987e5', '#eda100', '#e87ba4', '#b9aee0'
DISP, MONO = 'Bricolage Grotesque', 'JetBrains Mono'
config.background_color = BG

# ---------------------------------------------------------------- data
def svc(f): return {s['id']: s for s in json.loads((R / f).read_text())['services']}
SOAK, SOAK2, ASOAK = svc('r4_c_soak.json'), svc('r4_c2_soak.json'), svc('r4_aot_soak.json')
ROUND = svc('r4_c_round3.json')
def med(xs):
    xs = sorted(xs); n = len(xs); return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2
CPU = {k: med([s[k]['stats']['cpu_median_pct'] for s in (SOAK, SOAK2, ASOAK) if k in s]) for k in ('rust', 'go', 'cs10', 'cs11', 'cs11aot')}
# .NET 10 vs 11: mean of the two soaks where both ran in the same session, so the comparison is paired
for _k in ('cs10', 'cs11'): CPU[_k] = (SOAK[_k]['stats']['cpu_median_pct'] + SOAK2[_k]['stats']['cpu_median_pct']) / 2
def cpu_series(src, k): return [(t + 45, c) for t, m, c in src[k]['stats']['series'] if t <= 120]

# ---------------------------------------------------------------- text helpers (large enough for a phone)
def T(s, size=40, color=INK, weight=BOLD, font=DISP, **kw): return Text(s, font=font, font_size=size, color=color, weight=weight, **kw)
def M(s, size=26, color=MUTE, weight=NORMAL, **kw): return Text(s, font=MONO, font_size=size, color=color, weight=weight, **kw)
def box(label, w=2.6, h=0.8, color=INK, fill=BG, size=26, font=MONO):
    r = RoundedRectangle(corner_radius=0.12, width=w, height=h, stroke_color=color, stroke_width=3, fill_color=fill, fill_opacity=1)
    t = Text(label, font=font, font_size=size, color=color)
    if t.width > w - 0.3: t.scale_to_fit_width(w - 0.3)
    if t.height > h - 0.2: t.scale_to_fit_height(h - 0.2)
    return VGroup(r, t.move_to(r))
def chart(x0, x1, y1, w=11.0, h=4.6, xt=(45, 75, 105, 135, 165), yt=(0, 25, 50, 75, 100), xs='s', ys='%'):
    ax = Axes(x_range=[x0, x1, 30], y_range=[0, y1, 25], x_length=w, y_length=h, tips=False, axis_config={'color': HAIR, 'stroke_width': 2})
    grid = VGroup(*[DashedLine(ax.c2p(x0, y), ax.c2p(x1, y), color=HAIR, dash_length=0.06, stroke_width=1.5) for y in yt if y])
    xl = VGroup(*[M(f'{x} {xs}', 22).next_to(ax.c2p(x, 0), DOWN, buff=0.15) for x in xt])
    yl = VGroup(*[M(f'{y}{ys}', 22).next_to(ax.c2p(x0, y), LEFT, buff=0.15) for y in yt])
    return ax, VGroup(ax, grid, xl, yl)
def line_of(ax, pts, col, width=5):
    return ax.plot_line_graph([p[0] for p in pts], [min(p[1], 108) for p in pts], add_vertex_dots=False, line_color=col, stroke_width=width)

# ---------------------------------------------------------------- narration (Kokoro-82M with the pinned lexicon)
VO = HERE / 'vo'; VO.mkdir(exist_ok=True)
CUES = HERE / 'cues'; CUES.mkdir(exist_ok=True)
VOICE = os.environ.get('VOICE', 'am_michael'); SPEED = float(os.environ.get('SPEED', '1.0'))
SPOKEN = [(r'(\d)\s?ms\b', r'\1 milliseconds'), (r'(\d)\s?ns\b', r'\1 nanoseconds'), (r'(\d)%', r'\1 percent'), (r'(\d)×', r'\1 times'), (r'–', ' to ')]
def spoken(t):
    for a, b in SPOKEN: t = re.sub(a, b, t)
    return t
_k = None
def _engine():
    global _k
    if _k is None:
        from kokoro_onnx import Kokoro
        _k = Kokoro(str(HERE / 'tts' / 'kokoro-v1.0.onnx'), str(HERE / 'tts' / 'voices-v1.0.bin'))
    return _k
def lang(): return 'en-gb' if VOICE.startswith('b') else 'en-us'
def phonemes(text):
    from lexicon import to_phonemes
    return to_phonemes(text, lambda c: _engine().tokenizer.phonemize(c, lang()))
def tts(text):
    import soundfile as sf
    ph, _ = phonemes(spoken(text))
    f = VO / (hashlib.sha1(f'{VOICE}|{SPEED}|{ph}'.encode()).hexdigest()[:16] + '.wav')
    if not f.exists():
        a, sr = _engine().create(ph, voice=VOICE, speed=SPEED, lang=lang(), is_phonemes=True); sf.write(f, a, sr)
    i = sf.info(str(f)); return str(f), i.frames / i.samplerate

class Base(Scene):
    act = ''
    ref = ''   # where the evidence for this scene lives on the site, shown small in the corner
    def setup(self):
        self.audio_end, self.cues = 0.0, []
        self._keep = []
        if self.act: self._keep.append(M(self.act.upper(), 22, MUTE, BOLD).to_corner(UL, buff=0.45))
        if self.ref: self._keep.append(M('evidence › ' + self.ref, 20, MUTE).to_corner(DR, buff=0.32))
        if self._keep: self.add(*self._keep)
    def hold(self, extra=0.0):
        rem = self.audio_end - self.renderer.time + extra
        if rem > 0.05: self.wait(rem)
    def say(self, text, gap=0.4):
        """start a narration line now; animations keep running, the next say() waits for this one to finish"""
        self.hold()
        f, d = tts(text); self.add_sound(f)
        t0 = self.renderer.time; self.audio_end = t0 + d + gap
        self.cues.append((round(t0, 2), round(t0 + d, 2), text))
    def fade_all(self, keep_act=True):
        self.hold()
        mobs = [m for m in self.mobjects if not (keep_act and any(m is k for k in self._keep))]
        if mobs: self.play(*[FadeOut(m) for m in mobs], run_time=0.6)
    # ---- keep everything inside the frame: shrink and nudge anything that would be cropped
    SAFE_X, SAFE_Y = 6.75, 3.85
    def _fit(self, m):
        if not isinstance(m, Mobject) or m.width == 0: return
        if isinstance(m, (Axes, VGroup)) and any(isinstance(x, Axes) for x in m.get_family()): return   # charts are laid out explicitly
        if m.width > 2 * self.SAFE_X: m.scale_to_fit_width(2 * self.SAFE_X)
        if m.height > 2 * self.SAFE_Y: m.scale_to_fit_height(2 * self.SAFE_Y)
        dx = max(0, -self.SAFE_X - m.get_left()[0]) - max(0, m.get_right()[0] - self.SAFE_X)
        dy = max(0, -self.SAFE_Y - m.get_bottom()[1]) - max(0, m.get_top()[1] - self.SAFE_Y)
        if dx or dy: m.shift([dx, dy, 0])
    def play(self, *anims, **kw):
        for a in anims:
            mob = getattr(a, 'mobject', None)
            if isinstance(a, (FadeIn, Write, Create, GrowFromCenter)) and mob is not None and not os.environ.get("NOFIT"): self._fit(mob)
        super().play(*anims, **kw)
        if os.environ.get('CHECK'): self._report()
    def _report(self):
        out = []
        for m in self.mobjects:
            for x in m.get_family():
                if (isinstance(x, Text) or (isinstance(x, VMobject) and not x.submobjects and x.has_points())) and x.width > 0 and (x.get_left()[0] < -6.85 or x.get_right()[0] > 6.85 or x.get_top()[1] > 3.9 or x.get_bottom()[1] < -3.9):
                    out.append(f'{self.renderer.time:7.1f}s  {getattr(x, "text", type(x).__name__)[:50]!r}  x {x.get_left()[0]:.2f}..{x.get_right()[0]:.2f}  y {x.get_bottom()[1]:.2f}..{x.get_top()[1]:.2f}')
        if out:
            with open(CUES / f'overflow_{type(self).__name__}.txt', 'a') as f: f.write('\n'.join(sorted(set(out))) + '\n')
    def tear_down(self):
        (CUES / f'{type(self).__name__}.json').write_text(json.dumps({'cues': self.cues, 'duration': self.renderer.time}))

# ================================================================ ACT 1 · something strange happened
class A1Hook(Base):
    ref = '4 In containers › 8-minute soak'
    def construct(self):
        ax, frame = chart(45, 165, 110)
        frame.shift(DOWN * 0.35)
        bt = M('500 payments / s, steady', 26, GOOD, BOLD)
        badge = VGroup(RoundedRectangle(corner_radius=0.15, width=bt.width + 0.6, height=0.75, stroke_color=GOOD, stroke_width=2.5, fill_color=BG, fill_opacity=1), bt)
        bt.move_to(badge[0])
        who = T('C# service, one CPU, after a cold start', 34, INK, MEDIUM).to_corner(UL, buff=0.5)
        badge.to_corner(UR, buff=0.5).shift(DOWN * 0.75)
        jit = cpu_series(ASOAK, 'cs11')
        first = [p for p in jit if p[0] <= 88]; rest = [p for p in jit if p[0] >= 88]
        self.add(frame)
        self.say('At five hundred payments a second, our C# service was using eighty-five percent of its CPU.')
        self.play(FadeIn(who), FadeIn(badge), run_time=0.6)
        l1 = line_of(ax, first, C_JIT); self.play(Create(l1), run_time=3.2, rate_func=linear)
        hi = T('85%', 64, C_JIT).next_to(ax.c2p(60, 92), UP, buff=0.1)
        self.play(FadeIn(hi, scale=0.8))
        self.say('Ninety seconds later, it was down to fifty-two. Same code. Same traffic.')
        l2 = line_of(ax, rest, C_JIT); self.play(Create(l2), run_time=3.0, rate_func=linear)
        lo = T('52%', 64, C_JIT).next_to(ax.c2p(140, 56), UP, buff=0.1)
        self.play(FadeIn(lo, scale=0.8))
        self.say('So what changed? And if we had written it in Rust or Go instead, would it even matter?')
        q = T('?', 200, ACC).move_to(ax.c2p(105, 78))
        self.play(FadeIn(q, scale=0.5)); self.hold()
        self.play(FadeOut(VGroup(frame, l1, l2, hi, lo, q, who, badge)))
        self.say('We tested five builds, pushed three and a half million payments through them, and deliberately broke the payment provider.')
        chips = VGroup(*[VGroup(T(a, 76, c), M(b, 26, MUTE)).arrange(DOWN, buff=0.15) for a, b, c in
                         (('5', 'builds', INK), ('3.5 M', 'payments, all checked', GOOD), ('1', 'provider, broken on purpose', BAD))]).arrange(RIGHT, buff=1.1)
        if chips.width > 13: chips.scale_to_fit_width(13)
        self.play(LaggedStart(*[FadeIn(c, shift=UP * 0.2) for c in chips], lag_ratio=0.7), run_time=4)
        self.hold(); self.play(FadeOut(chips))
        t1 = T('C#, Rust and Go', 88); t2 = T('When does performance actually matter?', 52, ACC).next_to(t1, DOWN, buff=0.35)
        self.say('The answer was not as simple as the benchmark charts suggest.')
        self.play(Write(t1), run_time=1.0); self.play(FadeIn(t2, shift=UP * 0.2))
        self.hold(0.8); self.play(FadeOut(VGroup(t1, t2)))

# ================================================================ ACT 2 · what is the machine doing?
class A2Machine(Base):
    ref = 'Concepts › tiered JIT'
    act = 'Act 1 · why the CPU dropped'
    def construct(self):
        rows = [('Rust', 'rustc + LLVM', C_RUST, False), ('Go', 'go build', C_GO, False), ('C# · Native AOT', 'Roslyn → ILC', C_AOT, False), ('C# · JIT', 'Roslyn → IL', C_JIT, True)]
        split = 1.9
        line = DashedLine([split, 2.7, 0], [split, -2.9, 0], color=MUTE, dash_length=0.14)
        lab = VGroup(M('BEFORE IT STARTS', 22, MUTE, BOLD).next_to([split, 2.95, 0], LEFT, buff=0.2), M('WHILE IT RUNS', 22, MUTE, BOLD).next_to([split, 2.95, 0], RIGHT, buff=0.2))
        self.say('All three languages end up running machine code. The difference is when that machine code gets made.')
        self.play(Create(line), FadeIn(lab))
        built = []
        for i, (name, comp, col, jit) in enumerate(rows):
            y = 1.9 - i * 1.35
            nm = T(name, 32, col); nm.move_to([-6.8 + nm.width / 2, y, 0])
            b1 = box(comp, w=2.9, h=0.85, size=26).move_to([-1.2, y, 0])
            b2 = box('compiles hot code' if jit else 'machine code', w=3.6, h=0.85, size=26, color=ACC if jit else INK).move_to([4.4, y, 0])
            a = Arrow(b1.get_right(), b2.get_left(), buff=0.08, color=MUTE, stroke_width=3, max_tip_length_to_length_ratio=0.08)
            built.append(VGroup(nm, b1, a, b2))
        self.play(LaggedStart(*[FadeIn(b, shift=RIGHT * 0.3) for b in built[:3]], lag_ratio=0.4), run_time=2.2)
        self.say('Rust, Go, and C# compiled with Native AOT do all of it before the program starts.')
        self.hold()
        self.say('Regular C# ships an intermediate language, and the JIT compiler finishes the job while the service is already handling traffic.')
        self.play(FadeIn(built[3], shift=RIGHT * 0.3))
        self.play(Indicate(built[3][3], color=ACC, scale_factor=1.08))
        self.fade_all()
        # tiers: corrected wording, eligible hot methods move up
        self.say('It starts each method on quick, unoptimised code. The methods that run hot get profiled, then recompiled with full optimisation.')
        steps = [('Tier 0', 'quick code, so it can start', MUTE), ('Profile', 'records the real types', C_GO), ('Tier 1', 'optimised for this traffic', GOOD)]
        cards = VGroup(*[VGroup(box(a, w=3.4, h=1.0, size=34, color=c, font=DISP), T(b, 24, MUTE, MEDIUM)).arrange(DOWN, buff=0.25) for a, b, c in steps]).arrange(RIGHT, buff=0.75).shift(UP * 0.4)
        if cards.width > 13.2: cards.scale_to_fit_width(13.2)
        arr = VGroup(*[Arrow(cards[i][0].get_right(), cards[i + 1][0].get_left(), buff=0.1, color=MUTE, stroke_width=4) for i in range(2)])
        self.play(FadeIn(cards[0], shift=UP * 0.2)); self.play(GrowArrow(arr[0]), FadeIn(cards[1], shift=UP * 0.2)); self.play(GrowArrow(arr[1]), FadeIn(cards[2], shift=UP * 0.2))
        note = M('only methods that are called often move up the tiers', 26, MUTE).next_to(cards, DOWN, buff=0.8)
        self.play(FadeIn(note)); self.hold(); self.play(FadeOut(VGroup(cards, arr, note)))
        # back to the chart, now with the answer
        ax, frame = chart(45, 165, 110); frame.shift(DOWN * 0.35)
        jit = line_of(ax, cpu_series(ASOAK, 'cs11'), C_JIT); self.play(FadeIn(frame), FadeIn(jit))
        zone = Rectangle(width=ax.c2p(89, 0)[0] - ax.c2p(45, 0)[0], height=ax.c2p(0, 108)[1] - ax.c2p(0, 0)[1], fill_color=C_JIT, fill_opacity=0.12, stroke_width=0)
        zone.move_to(ax.c2p(45, 0), aligned_edge=DL)
        zl = T('serving traffic + compiling', 30, C_JIT).move_to(ax.c2p(70, 15))
        self.say('That eighty-five percent is the service doing its real work, and compiling at the same time.')
        self.play(FadeIn(zone), FadeIn(zl)); self.hold()
        aot = line_of(ax, cpu_series(ASOAK, 'cs11aot'), C_AOT); gol = line_of(ax, cpu_series(SOAK, 'go'), C_GO)
        leg = VGroup(*[VGroup(Line(ORIGIN, RIGHT * 0.5, color=c, stroke_width=7), M(l, 24, c, BOLD)).arrange(RIGHT, buff=0.15)
                       for l, c in (('C# JIT', C_JIT), ('C# Native AOT', C_AOT), ('Go', C_GO))]).arrange(RIGHT, buff=0.7).to_corner(UR, buff=0.5)
        self.say('Native AOT and Go have nothing left to compile, so they never show that warm-up.')
        self.play(Create(aot), Create(gol), FadeIn(leg), run_time=2.5); self.hold()
        self.say('So compilation explains how the service starts. But what happens once the code is warm? We started with the smallest workload there is: a loop that adds numbers.')
        self.hold(); self.fade_all()

# ================================================================ ACT 3 · what the optimiser does
CS_LOOP = ['add   eax, dword ptr [rcx]', 'add   rcx, 4', 'dec   edx', 'jne   loop']
RS_LOOP = ['movdqu xmm2, [rcx + 4*rax]', 'paddd  xmm1, xmm2', 'movdqu xmm2, [rcx + 4*rax + 16]', 'paddd  xmm0, xmm2', 'add    rax, 8', 'jne    loop']
class A3Loop(Base):
    ref = '1 Machine code › vectorise'
    act = 'Act 2 · the same loop, two compilers'
    def construct(self):
        def lane(y, label, col):
            cells = VGroup(*[box(str(v), w=0.66, h=0.66, size=28) for v in (3, 1, 4, 1, 5, 9, 2, 6)]).arrange(RIGHT, buff=0.08)
            cells.move_to([-6.7 + 0.0, y, 0], aligned_edge=LEFT); t = T(label, 30, col).next_to(cells, UP, buff=0.25).align_to(cells, LEFT)
            return cells, t
        c1, t1 = lane(1.6, 'C# · .NET 10: one per pass', C_JIT)
        c2, t2 = lane(-1.4, 'Rust · LLVM: four per instruction', C_RUST)
        def code(lines, col, hot):
            g = VGroup(*[M(l, 23, col if i in hot else MUTE, BOLD if i in hot else NORMAL) for i, l in enumerate(lines)]).arrange(DOWN, aligned_edge=LEFT, buff=0.12)
            panel = SurroundingRectangle(g, buff=0.25, color=HAIR, corner_radius=0.12, stroke_width=2)
            return VGroup(panel, g)
        k1 = code(CS_LOOP, C_JIT, {0}); k1.move_to([6.6 - k1.width / 2, 1.6, 0]); k2 = code(RS_LOOP, C_RUST, {1, 3}); k2.move_to([6.6 - k2.width / 2, -1.45, 0])
        src = M('the real loop bodies, from the set 1 listings', 22).next_to(k2, DOWN, buff=0.25).align_to(k2, RIGHT)
        self.say('Here is the machine code each compiler produced for the same loop.')
        self.play(FadeIn(c1), FadeIn(t1), FadeIn(c2), FadeIn(t2), FadeIn(k1), FadeIn(k2), FadeIn(src), run_time=1.0)
        self.say('The .NET 10 JIT adds one number per pass. Rust\'s compiler proved the loop safe to batch, and adds four at a time, twice per pass.')
        for i in range(8):
            an = [c1[i][0].animate.set_fill(C_JIT, 0.4)]
            if i in (0, 4): an += [c2[j][0].animate.set_fill(C_RUST, 0.45) for j in range(i, i + 4)]
            self.play(*an, Indicate(k1[1][0], color=C_JIT, scale_factor=1.04), run_time=0.5)
        self.hold(); self.play(FadeOut(VGroup(c1, t1, c2, t2, k1, k2, src)))
        data = [('Rust', 0.104, C_RUST), ('Go', 0.574, C_GO), ('C# .NET 10', 0.763, C_JIT)]
        bars = VGroup()
        for i, (n, v, c) in enumerate(data):
            y = 1.2 - i * 1.25
            lab = T(n, 34, c); lab.move_to([-6.6 + lab.width / 2, y, 0])
            bar = Rectangle(width=v * 9, height=0.75, fill_color=c, fill_opacity=1, stroke_width=0).move_to([-3.4, y, 0], aligned_edge=LEFT)
            val = M(f'{v:.2f} ns', 32, INK, BOLD).next_to(bar, RIGHT, buff=0.25)
            bars.add(VGroup(lab, bar, val))
        head = T('Time per number added', 36, MUTE, MEDIUM).to_edge(UP, buff=1.1)
        self.say('On this loop, Rust was about seven times faster: a tenth of a nanosecond per number, against three quarters.')
        self.play(FadeIn(head), LaggedStart(*[AnimationGroup(FadeIn(b[0]), GrowFromEdge(b[1], LEFT), FadeIn(b[2])) for b in bars], lag_ratio=0.35), run_time=2.4)
        big = T('7×', 120, C_RUST).move_to([4.6, -2.3, 0]); self.play(FadeIn(big, scale=0.6)); self.hold()
        self.say('Seven times sounds enormous. But that is one tiny loop, and a payment request does much more than add numbers.')
        self.hold(); self.fade_all()

class A3Net11(Base):
    ref = '2 .NET 11 claims'
    act = 'Act 2 · what .NET 11 changes'
    def construct(self):
        self.say('.NET 11 changes the machine code too. Two of its changes showed up clearly in our benchmarks.')
        def card(title, before, after, unit, gain, note, col):
            r = RoundedRectangle(corner_radius=0.2, width=6.2, height=4.6, stroke_color=HAIR, stroke_width=2.5)
            t = T(title, 36, INK).move_to(r.get_top() + DOWN * 0.6)
            b = M(f'.NET 10   {before}', 30, MUTE, BOLD).move_to(r.get_center() + UP * 0.45)
            a = M(f'.NET 11   {after}', 30, col, BOLD).move_to(r.get_center() + DOWN * 0.25)
            u = M(unit, 22, MUTE).next_to(a, DOWN, buff=0.15)
            g = T(gain, 52, col).move_to(r.get_bottom() + UP * 1.0)
            n = M(note, 19, MUTE).move_to(r.get_bottom() + UP * 0.35)
            if n.width > 5.8: n.scale_to_fit_width(5.8)
            return VGroup(r, t, b, a, u, g, n)
        c1 = card('Devirtualisation', '4.73 ns', '0.72 ns', 'per generic virtual call', '6.5× faster', 'our benchmark · Microsoft\'s example shows ~4×', GOOD).move_to(LEFT * 3.4 + DOWN * 0.2)
        c2 = card('Runtime async', '18.1 ns · 72 B', '4.4 ns · 0 B', 'per await, in our ten-level chain', '4× cheaper', 'opt-in in RC2', ACC).move_to(RIGHT * 3.4 + DOWN * 0.2)
        self.play(FadeIn(c1[0]), FadeIn(c1[1]), FadeIn(c1[2]))
        self.say('In our generic virtual call test, the JIT could finally see the exact type and inline the call: six and a half times faster. Microsoft\'s own example shows about four, so the gain depends on your code.')
        self.play(FadeIn(c1[3], shift=LEFT * 0.2), FadeIn(c1[4])); self.play(FadeIn(c1[5], scale=0.8), FadeIn(c1[6])); self.hold()
        self.play(FadeIn(c2[0]), FadeIn(c2[1]), FadeIn(c2[2]))
        self.say('Runtime async made an await in our test chain about four times cheaper, and removed its allocation. In release candidate two, you still have to switch it on.')
        self.play(FadeIn(c2[3], shift=LEFT * 0.2), FadeIn(c2[4])); self.play(FadeIn(c2[5], scale=0.8), FadeIn(c2[6])); self.hold()
        self.say('Big wins, on small pieces of code. So we started adding the things a real API has to deal with.')
        self.hold(); self.fade_all()

# ================================================================ ACT 4 · does any of it survive production?
class A4Gap(Base):
    ref = 'Start › the main finding'
    act = 'Act 3 · adding the real world'
    def construct(self):
        rows = [('A loop that adds numbers', 'time per number', 'Rust 0.10 ns', 'C# 0.76 ns', 7.3),
                ('+ HTTP and JSON, in memory', 'requests per second', 'Rust 43,420', 'C# 34,425', 1.26),
                ('+ Postgres, Redis, a provider', 'median response time', 'Rust 28.1 ms', 'slowest 29.6 ms', 1.05)]
        x0, unit = -0.4, 0.78
        base = DashedLine([x0, 2.6, 0], [x0, -1.9, 0], color=MUTE, dash_length=0.1)
        bl = M('1× = the same', 22, MUTE).next_to(base, UP, buff=0.1)
        self.say('Each time we added something a real service needs, we measured how far apart the fastest and slowest builds were.')
        self.play(Create(base), FadeIn(bl))
        for i, (n, m, a, b, v) in enumerate(rows):
            y = 1.8 - i * 1.5
            lab = VGroup(T(n, 32, INK), M(m, 22)).arrange(DOWN, aligned_edge=LEFT, buff=0.08); lab.move_to([-6.8 + lab.width / 2, y, 0])
            bar = Rectangle(width=(v - 1) * unit + 0.08, height=0.62, fill_color=ACC, fill_opacity=1, stroke_width=0).move_to([x0, y + 0.1, 0], aligned_edge=LEFT)
            val = T(f'{v:g}×', 40, ACC).next_to(bar, RIGHT, buff=0.25)
            raw = M(f'{a}  vs  {b}', 22, MUTE).next_to(bar, DOWN, buff=0.12).align_to(bar, LEFT)
            if i == 0: self.say('A loop: seven times apart.')
            elif i == 1: self.say('An in-memory API with HTTP and JSON: about a quarter.')
            else: self.say('Add a database, a cache and a payment provider, and the median response time is within five percent.')
            self.play(FadeIn(lab), GrowFromEdge(bar, LEFT), FadeIn(val), FadeIn(raw), run_time=1.1); self.hold()
        self.fade_all()
        self.say('But the median is not the whole story. At the same traffic, the builds still differed in their slowest requests, and in how much CPU they burned.')
        heads = VGroup(M('slowest 1 in 100 (p99)', 26, MUTE, BOLD), M('CPU at 500 payments / s', 26, MUTE, BOLD)).arrange(RIGHT, buff=2.2).shift(UP * 2.3 + RIGHT * 0.5)
        data = [('Rust', 122, CPU['rust'], C_RUST), ('Go', 127, CPU['go'], C_GO), ('C# .NET 11', 147, CPU['cs11'], C_JIT), ('C# .NET 10', 129, CPU['cs10'], C_CS10)]
        g = VGroup()
        for i, (n, p, c, col) in enumerate(data):
            y = 1.3 - i * 1.0
            nm = T(n, 32, col); nm.move_to([-6.7 + nm.width / 2, y, 0])
            g.add(VGroup(nm, M(f'{p} ms', 34, INK, BOLD).move_to([heads[0].get_x(), y, 0]),
                         Rectangle(width=c * 0.05, height=0.5, fill_color=col, fill_opacity=1, stroke_width=0).move_to([heads[1].get_left()[0], y, 0], aligned_edge=LEFT),
                         M(f'{c:.0f}%', 30, INK, BOLD).move_to([heads[1].get_left()[0] + c * 0.05 + 0.6, y, 0])))
        self.play(FadeIn(heads), LaggedStart(*[FadeIn(r, shift=UP * 0.15) for r in g], lag_ratio=0.3), run_time=2.0)
        self.hold(); self.fade_all()

class A4Outage(Base):
    ref = '4 In containers › provider outage'
    act = 'Act 3 · breaking the provider'
    def construct(self):
        S = ROUND['go']; ser = S['degrade']['series'][:90]
        steps = ['client', 'JWT +\nRedis', 'Postgres\ninsert', 'payment\nprovider', 'Postgres\ncapture', 'reply']
        bs = VGroup(*[box(s, w=1.9, h=1.15, size=24, font=DISP) for s in steps]).arrange(RIGHT, buff=0.38).shift(UP * 2.2)
        arrs = VGroup(*[Arrow(bs[i].get_right(), bs[i + 1].get_left(), buff=0.05, stroke_width=3, color=MUTE, max_tip_length_to_length_ratio=0.4) for i in range(5)])
        timeout = M('1 s timeout', 22, WARN, BOLD).next_to(bs[3], UP, buff=0.15)
        self.say('Then we did what production eventually does to every service. One payment service, five hundred payments a second, and a simulated payment provider that is about to have a very bad thirty seconds.')
        self.play(LaggedStart(*[FadeIn(b, shift=DOWN * 0.15) for b in bs], lag_ratio=0.12), Create(arrs), FadeIn(timeout), run_time=1.6)
        # live panel: latency chart + counters, driven by the measured per-second series (Go, round 3)
        ax = Axes(x_range=[0, 90, 30], y_range=[0, 400, 100], x_length=7.0, y_length=3.2, tips=False, axis_config={'color': HAIR, 'stroke_width': 2}).move_to([-1.9, -1.25, 0])
        xl = VGroup(*[M(f'{x} s', 20).next_to(ax.c2p(x, 0), DOWN, buff=0.12) for x in (0, 30, 60, 90)])
        yl = VGroup(*[M(f'{y} ms', 20).next_to(ax.c2p(0, y), LEFT, buff=0.12) for y in (0, 200, 400)])
        shade = Rectangle(width=ax.c2p(60, 0)[0] - ax.c2p(30, 0)[0], height=ax.c2p(0, 400)[1] - ax.c2p(0, 0)[1], fill_color=BAD, fill_opacity=0.12, stroke_width=0).move_to(ax.c2p(30, 0), aligned_edge=DL)
        ctitle = M('median response time', 22, MUTE, BOLD).next_to(ax, UP, buff=0.15).align_to(ax, LEFT)
        t = ValueTracker(0)
        def curve():
            k = max(2, int(t.get_value()) + 1)
            pts = [(p['t'], min(p['p50_ms'], 400)) for p in ser[:k]]
            return ax.plot_line_graph([p[0] for p in pts], [p[1] for p in pts], add_vertex_dots=False, line_color=C_GO, stroke_width=5)
        live = always_redraw(curve)
        cum = [0]
        for p in ser: cum.append(cum[-1] + p['errors'])
        mem = [(round(tt), m) for tt, m, _ in S['degrade_stats']['series']]
        def memat(x): return min((abs(tt - x), m) for tt, m in mem)[1] if mem else 0
        def counters():
            x = int(min(t.get_value(), 89))
            g = VGroup(VGroup(M('failed fast', 22, MUTE), T(f'{cum[x + 1]:,}', 48, BAD)).arrange(DOWN, aligned_edge=LEFT, buff=0.05),
                       VGroup(M('memory (limit 512 MB)', 22, MUTE), T(f'{memat(x):.0f} MB', 48, GOOD)).arrange(DOWN, aligned_edge=LEFT, buff=0.05),
                       VGroup(M('provider', 22, MUTE), T('degraded' if 30 <= x < 60 else 'healthy', 48, BAD if 30 <= x < 60 else GOOD)).arrange(DOWN, aligned_edge=LEFT, buff=0.05))
            return g.arrange(DOWN, aligned_edge=LEFT, buff=0.35).move_to([4.7, -1.25, 0])
        ctr = always_redraw(counters)
        prov = bs[3]
        prov.add_updater(lambda m: m[0].set_stroke(BAD if 30 <= t.get_value() < 60 else INK).set_fill(BAD if 30 <= t.get_value() < 60 else BG, 0.25 if 30 <= t.get_value() < 60 else 1))
        # request dots flow along the pipeline; during the outage some stop at the provider and turn red
        path_y = bs[0].get_bottom()[1] - 0.3
        xs_ = [b.get_x() for b in bs]
        dots = VGroup(*[Dot(radius=0.08, color=GOOD) for _ in range(14)])
        def flow(g, dt):
            tv = t.get_value()
            for i, d in enumerate(g):
                ph = (tv * 0.9 + i / len(g)) % 1.0
                x = xs_[0] + ph * (xs_[-1] - xs_[0])
                bad = 30 <= tv < 60 and i % 4 == 0
                if bad: x = min(x, xs_[3])
                d.move_to([x, path_y, 0]).set_color(BAD if bad and x >= xs_[3] - 0.01 else GOOD)
        dots.add_updater(flow)
        self.play(FadeIn(VGroup(ax, xl, yl, ctitle)), FadeIn(dots))
        self.add(live, ctr)
        self.play(t.animate.set_value(29), run_time=4.0, rate_func=linear)
        self.say('At thirty seconds, the provider became ten times slower, and one call in ten simply hung.')
        self.play(FadeIn(shade), run_time=0.4)
        self.play(t.animate.set_value(45), run_time=4.5, rate_func=linear)
        self.say('Latency jumped to the provider\'s new speed. Every hung call was cut off at its one-second timeout and failed fast, instead of piling up. Memory stayed far below the limit.')
        self.play(t.animate.set_value(60), run_time=5.0, rate_func=linear)
        self.hold()
        self.say('When the provider recovered, the service recovered with it, within a second.')
        self.play(t.animate.set_value(90), run_time=4.0, rate_func=linear); self.hold()
        dots.clear_updaters(); prov.clear_updaters()
        self.fade_all()
        # the ledger check as the result of the experiment
        cap, bal = S['degrade_integrity']['captured'], S['degrade_integrity']['balance_count']
        self.say('Then came the real test. Every captured payment had to appear exactly once in a merchant balance.')
        l1 = VGroup(M('captured payments', 28, MUTE), T(f'{cap:,}', 80, INK)).arrange(DOWN, buff=0.1).move_to(LEFT * 3.2 + UP * 0.6)
        l2 = VGroup(M('counted in merchant balances', 28, MUTE), T(f'{bal:,}', 80, INK)).arrange(DOWN, buff=0.1).move_to(RIGHT * 3.2 + UP * 0.6)
        eq = T('=', 90, GOOD).move_to(UP * 0.4)
        self.play(FadeIn(l1, shift=UP * 0.2)); self.play(FadeIn(l2, shift=UP * 0.2)); self.play(FadeIn(eq, scale=0.6))
        allr = T('Every build, every run: 3.5 million payments, none lost, none counted twice', 34, GOOD).shift(DOWN * 1.8)
        if allr.width > 13: allr.scale_to_fit_width(13)
        self.hold()
        self.say('It did, for all five builds, in every run. Three and a half million payments: none lost, none counted twice. On reliability, the language made no difference. Timeouts and bounded resources did.')
        self.play(FadeIn(allr, shift=UP * 0.2)); self.hold(); self.fade_all()

class A4Load(Base):
    ref = 'Concepts › open-loop load'
    act = 'Act 3 · how we measured latency'
    def construct(self):
        stall = (-0.6, 2.6)
        def lane(y, title):
            t = T(title, 30, INK); t.move_to([-6.7 + t.width / 2, y + 0.85, 0])
            r = Rectangle(width=stall[1] - stall[0], height=1.7, fill_color=ACC, fill_opacity=0.14, stroke_width=0).move_to([(stall[0] + stall[1]) / 2, y - 0.35, 0])
            lab = M('server stalls', 22, ACC).move_to(r.get_corner(UR) + LEFT * 1.1 + DOWN * 0.22)
            return VGroup(t, Line([-6.7, y, 0], [6.7, y, 0], color=HAIR, stroke_width=2), r, lab)
        L1, L2 = lane(1.5, 'Load test that waits for each answer'), lane(-1.4, 'Real users: requests keep arriving on schedule')
        self.say('One more thing about measuring. How a load test sends requests decides what latency it sees.')
        self.play(FadeIn(L1), FadeIn(L2))
        reqs, x = [], -6.5
        while x < 6.2:
            late = stall[0] <= x < stall[1]; end = stall[1] + 0.15 if late else x + 0.45
            reqs.append(VGroup(Dot([x, 1.5, 0], radius=0.08, color=INK), Line([x, 1.5, 0], [end, 1.5, 0], color=BAD if late else INK, stroke_width=6 if late else 3))); x = end + 0.3
        self.say('A test that waits for each answer sends nothing while the server stalls, so it records one slow request.')
        self.play(LaggedStart(*[Create(r) for r in reqs], lag_ratio=0.5), run_time=3.5)
        one = M('1 slow request recorded', 24, BAD, BOLD).next_to(L1[2], DOWN, buff=0.12); self.play(FadeIn(one)); self.hold()
        reqs2, n = [], 0
        for i in range(17):
            x = -6.5 + i * 0.75; late = stall[0] <= x < stall[1]; y = -1.4 - (n * 0.27 if late else 0)
            if late: n += 1
            reqs2.append(VGroup(Dot([x, y, 0], radius=0.08, color=INK), Line([x, y, 0], [stall[1] + 0.15 if late else x + 0.45, y, 0], color=BAD if late else INK, stroke_width=6 if late else 3)))
        self.say('Real users keep arriving, so every one of them waits. All the latency numbers in this video were measured the second way.')
        self.play(LaggedStart(*[Create(r) for r in reqs2], lag_ratio=0.5), run_time=3.5)
        many = M(f'{n} slow requests recorded', 24, BAD, BOLD).next_to(L2[2], DOWN, buff=0.12); self.play(FadeIn(many))
        self.hold(); self.fade_all()

# ================================================================ ACT 3b · three results that pushed back
NET10_BIGMUL = [('mulx  r10, r11, r10', 'k'), ('…sign fix-up…', 'm'), ('add   rax, r10', 'g')]
NET11_BIGMUL = [('mov   qword ptr [rsp], rax', 'b'), ('imul  rdx:rax, qword ptr [rcx]', 'g'), ('xor   rax, rdx', 'm'), ('add   rax, qword ptr [rsp]', 'b')]
class A4Surprises(Base):
    act = 'Act 3 · results that pushed back'
    ref = 'Start › where the tests pushed back'
    def construct(self):
        self.say('Three results pushed back on the simple story. First, the same .NET 11 build went in opposite directions.')
        def panel(x, title, sub, rows, unit, scale, delta, col):
            t = T(title, 34, INK).move_to([x, 2.3, 0]); st = M(sub, 22, MUTE).next_to(t, DOWN, buff=0.12)
            g = VGroup()
            for i, (n, v, c) in enumerate(rows):
                y = 0.9 - i * 0.95
                lab = T(n, 28, c); lab.move_to([x - 3.0 + lab.width / 2, y, 0])
                bar = Rectangle(width=v * scale, height=0.55, fill_color=c, fill_opacity=1, stroke_width=0).move_to([x - 1.2, y, 0], aligned_edge=LEFT)
                g.add(VGroup(lab, bar, M(f'{v:g} {unit}', 26, INK, BOLD).next_to(bar, RIGHT, buff=0.18)))
            d = T(delta, 72, col).move_to([x, -1.6, 0])
            return t, st, g, d
        L = panel(-3.5, 'Plain in-memory API', 'set 3 · CPU time per request', [('.NET 10', 90.5, C_CS10), ('.NET 11', 100.4, C_JIT)], 'µs', 0.022, '+11%', BAD)
        Rr = panel(3.5, 'Payment service', 'set 4 · CPU at 500 payments / s', [('.NET 10', 72, C_CS10), ('.NET 11', 53, C_JIT)], '%', 0.028, '−26%', GOOD)
        div = DashedLine([0, 2.7, 0], [0, -2.4, 0], color=HAIR, dash_length=0.1)
        self.play(FadeIn(div), FadeIn(L[0]), FadeIn(L[1]), FadeIn(Rr[0]), FadeIn(Rr[1]))
        self.say('In the plain in-memory API, it used about eleven percent more CPU per request than .NET 10.')
        self.play(LaggedStart(*[AnimationGroup(FadeIn(r[0]), GrowFromEdge(r[1], LEFT), FadeIn(r[2])) for r in L[2]], lag_ratio=0.4), run_time=1.6)
        self.play(FadeIn(L[3], scale=0.7)); self.hold()
        self.say('In the payment service, about a quarter less. One workload does not predict another.')
        self.play(LaggedStart(*[AnimationGroup(FadeIn(r[0]), GrowFromEdge(r[1], LEFT), FadeIn(r[2])) for r in Rr[2]], lag_ratio=0.4), run_time=1.6)
        self.play(FadeIn(Rr[3], scale=0.7)); self.hold(); self.fade_all()
        # BigMul: shorter code, slower loop
        colmap = {'k': INK, 'm': MUTE, 'g': GOOD, 'b': BAD}
        def listing(title, lines, x):
            head = T(title, 32, INK).move_to([x, 2.4, 0])
            g = VGroup(*[M(l, 26, colmap[c], BOLD if c in 'gb' else NORMAL) for l, c in lines]).arrange(DOWN, aligned_edge=LEFT, buff=0.22)
            g.next_to(head, DOWN, buff=0.45)
            return VGroup(head, SurroundingRectangle(g, buff=0.3, color=HAIR, corner_radius=0.12, stroke_width=2), g)
        a = listing('.NET 10 · 25 instructions', NET10_BIGMUL, -3.5); b = listing('.NET 11 · 20 instructions', NET11_BIGMUL, 3.3)
        self.say('Second, .NET 11 turns Math dot BigMul into a single multiply instruction. The loop got shorter.')
        self.play(FadeIn(a), FadeIn(b)); self.hold()
        note = VGroup(M('total kept in a register', 22, GOOD).next_to(a[1], DOWN, buff=0.25),
                      M('total stored to memory and read back, every pass', 22, BAD).next_to(b[1], DOWN, buff=0.25))
        res = T('1.05 → 1.38 ns per multiply:  31% slower', 44, BAD).move_to([0, -2.6, 0])
        self.say('And thirty-one percent slower. The running total now goes out to memory and back on every pass, so each step has to wait for the one before it.')
        self.play(Indicate(b[2][0], color=BAD), Indicate(b[2][3], color=BAD), FadeIn(note)); self.play(FadeIn(res, shift=UP * 0.2)); self.hold(); self.fade_all()
        # the run that hung
        S = svc('r4_aot_round6.json')['cs10aot']; ser = S['degrade']['series'][:90]
        ax = Axes(x_range=[0, 90, 30], y_range=[0, 55, 25], x_length=8.2, y_length=3.8, tips=False, axis_config={'color': HAIR, 'stroke_width': 2}).move_to([-1.9, -0.35, 0])
        xl = VGroup(*[M(f'{x} s', 20).next_to(ax.c2p(x, 0), DOWN, buff=0.12) for x in (0, 30, 60, 90)])
        yl = VGroup(*[M(f'{y} s', 20).next_to(ax.c2p(0, y), LEFT, buff=0.12) for y in (0, 25, 50)])
        shade = Rectangle(width=ax.c2p(60, 0)[0] - ax.c2p(30, 0)[0], height=ax.c2p(0, 55)[1] - ax.c2p(0, 0)[1], fill_color=BAD, fill_opacity=0.1, stroke_width=0).move_to(ax.c2p(30, 0), aligned_edge=DL)
        head = T('.NET 10 Native AOT, round 2 of 5: median response time', 30, INK).next_to(ax, UP, buff=0.35).align_to(ax, LEFT)
        ln = ax.plot_line_graph([p['t'] for p in ser], [min(p['p50_ms'] / 1000, 55) for p in ser], add_vertex_dots=False, line_color=C_CS10, stroke_width=5)
        self.say('Third, in one of five rounds, .NET 10 Native AOT stopped answering near the end of the outage, and stayed stuck until the test ended.')
        self.play(FadeIn(VGroup(ax, xl, yl, shade, head))); self.play(Create(ln), run_time=3.0, rate_func=linear)
        facts = VGroup(VGroup(M('timed out', 22, MUTE), T(f"{S['degrade']['codes'].get('0', 0):,}", 52, BAD)).arrange(DOWN, aligned_edge=LEFT, buff=0.05),
                       VGroup(M('CPU while stuck', 22, MUTE), T('≈ 30%', 52, WARN)).arrange(DOWN, aligned_edge=LEFT, buff=0.05),
                       VGroup(M('next 3 rounds', 22, MUTE), T('clean', 52, GOOD)).arrange(DOWN, aligned_edge=LEFT, buff=0.05)).arrange(DOWN, aligned_edge=LEFT, buff=0.35).move_to([4.9, -0.4, 0])
        self.say('Fourteen thousand requests timed out while its CPU sat mostly idle. Three more rounds, with extra diagnostics, were clean, and the cause is still open.')
        self.play(LaggedStart(*[FadeIn(f, shift=LEFT * 0.2) for f in facts], lag_ratio=0.5), run_time=2.0); self.hold()
        self.say('We report it anyway. One stalled run is exactly what a single benchmark would hide.')
        self.hold(); self.fade_all()

# ================================================================ ACT 5 · which would you deploy?
class A5Deploy(Base):
    ref = '4 In containers › NativeAOT'
    act = 'Act 4 · which one would you deploy?'
    def construct(self):
        self.say('So which C# would you deploy: the default JIT, or Native AOT? Here are the trade-offs, one at a time.')
        hj = T('JIT', 40, C_JIT).move_to([1.4, 2.4, 0]); ha = T('Native AOT', 40, C_AOT).move_to([5.0, 2.4, 0])
        self.play(FadeIn(hj), FadeIn(ha))
        rows = [('Ready after a cold start', '1.06 s', '0.47 s', 'aot', 'Native AOT is ready in under half a second, like Go and Rust. The JIT build needs just over one.'),
                ('Memory before any traffic', '32 MB', '19 MB', 'aot', 'It idles in about forty percent less memory.'),
                ('Most payments per second', '1,451', '1,364', 'jit', 'But once the JIT has warmed up, it handles about six percent more payments at its peak.')]
        for i, (lab, j, a, win, line) in enumerate(rows):
            y = 1.2 - i * 1.35
            l = T(lab, 34, INK, MEDIUM); l.move_to([-6.7 + l.width / 2, y, 0])
            vj = T(j, 56, C_JIT if win == 'jit' else MUTE).move_to([1.4, y, 0]); va = T(a, 56, C_AOT if win == 'aot' else MUTE).move_to([5.0, y, 0])
            self.say(line)
            self.play(FadeIn(l), FadeIn(vj), FadeIn(va, shift=LEFT * 0.2), run_time=0.8)
            self.play(Circumscribe(va if win == 'aot' else vj, color=GOOD, buff=0.12), run_time=0.9); self.hold()
        self.fade_all()
        # cost: CPU time per payment, from the soak CPU at a fixed 500 payments/s
        self.say('What about efficiency? At a fixed five hundred payments a second, CPU time per payment shows how much compute each payment needs. Your bill also depends on memory, instance size, and how you buy capacity.')
        data = [('Rust', CPU['rust'], C_RUST), ('Go', CPU['go'], C_GO), ('C# .NET 11 · AOT', CPU['cs11aot'], C_AOT), ('C# .NET 11 · JIT', CPU['cs11'], C_JIT), ('C# .NET 10 · JIT', CPU['cs10'], C_CS10)]
        head = T('CPU time per payment, once warm', 36, MUTE, MEDIUM).to_edge(UP, buff=1.1)
        g = VGroup()
        for i, (n, c, col) in enumerate(data):
            ms = c / 100 / 500 * 1000; y = 1.6 - i * 0.95
            lab = T(n, 30, col); lab.move_to([-6.7 + lab.width / 2, y, 0])
            bar = Rectangle(width=ms * 4.4, height=0.55, fill_color=col, fill_opacity=1, stroke_width=0).move_to([-2.0, y, 0], aligned_edge=LEFT)
            g.add(VGroup(lab, bar, M(f'{ms:.2f} ms', 30, INK, BOLD).next_to(bar, RIGHT, buff=0.2)))
        self.play(FadeIn(head), LaggedStart(*[AnimationGroup(FadeIn(r[0]), GrowFromEdge(r[1], LEFT), FadeIn(r[2])) for r in g], lag_ratio=0.3), run_time=2.6)
        self.say('Rust and Go do the same work for the least CPU. C# on .NET 11 costs about a third more. On .NET 10, about eighty percent more.')
        self.hold(); self.fade_all()
        # back to the opening graph: .NET 10 vs .NET 11
        ax, frame = chart(45, 165, 110); frame.shift(DOWN * 0.35)
        l11 = line_of(ax, cpu_series(ASOAK, 'cs11'), C_JIT); l10 = line_of(ax, cpu_series(SOAK, 'cs10'), C_CS10)
        leg = VGroup(*[VGroup(Line(ORIGIN, RIGHT * 0.5, color=c, stroke_width=7), M(l, 24, c, BOLD)).arrange(RIGHT, buff=0.15)
                       for l, c in (('.NET 10', C_CS10), ('.NET 11 RC2', C_JIT))]).arrange(RIGHT, buff=0.7).to_corner(UR, buff=0.5)
        self.say('And the graph we started with? Here is the same service on .NET 10.')
        self.play(FadeIn(frame), FadeIn(l11), FadeIn(leg)); self.play(Create(l10), run_time=2.5)
        big = T(f'−{(1 - round(CPU["cs11"]) / round(CPU["cs10"])) * 100:.0f}% CPU', 64, GOOD).move_to(ax.c2p(130, 95))
        self.say('Settled, it used seventy-two percent of its CPU. .NET 11 needed fifty-three for the same traffic: about a quarter less, in our tests, on a release candidate.')
        self.play(FadeIn(big, scale=0.7)); self.hold(); self.fade_all()

class A5End(Base):
    def construct(self):
        q = T('So which language was fastest?', 64)
        self.say('So, which language was fastest? That depends on what we asked it to do.')
        self.play(Write(q), run_time=1.2); self.hold(); self.play(q.animate.scale(0.6).to_edge(UP, buff=0.7))
        lines = [('In a tight loop, the machine code mattered enormously.', '7×'),
                 ('With a database in the path, the median barely moved.', '5%'),
                 ('When the provider failed, discipline mattered, not language.', '0 lost')]
        said = ['In a tight loop, the generated machine code mattered enormously.',
                'Once a database was in the path, the median barely moved, but CPU cost and start-up still did.',
                'And when the provider failed, every build depended on the same discipline: timeouts, bounded resources, and recovery.']
        g = VGroup()
        for i, ((l, n), s) in enumerate(zip(lines, said)):
            row = VGroup(T(n, 48, ACC), T(l, 34, INK, MEDIUM)).arrange(RIGHT, buff=0.5)
            if row.width > 12.8: row.scale_to_fit_width(12.8)
            row.move_to([0, 1.2 - i * 1.3, 0]).align_to([-6.4, 0, 0], LEFT)
            self.say(s); self.play(FadeIn(row, shift=UP * 0.2)); self.hold(); g.add(row)
        self.play(FadeOut(g), FadeOut(q))
        k1 = T('A fast instruction is not a fast request.', 48); k2 = T('A fast request is not an efficient service.', 48, ACC).next_to(k1, DOWN, buff=0.35)
        self.say('A fast instruction is not necessarily a fast request. And a fast request is not necessarily an efficient, reliable service. The right benchmark is the one that measures the problem you are actually trying to solve.')
        self.play(FadeIn(k1, shift=UP * 0.2)); self.wait(2.5); self.play(FadeIn(k2, shift=UP * 0.2)); self.hold(); self.play(FadeOut(VGroup(k1, k2)))
        spec = VGroup(T('Compiler probes', 64),
                      M('Intel i5-10300H laptop · Docker Desktop VM, 4 CPUs · each service 1 CPU, 512 MB', 24, MUTE),
                      M('.NET 10.0.12 · .NET 11 RC2 · Go 1.27.2 · Rust 1.99 · Postgres 17 · Redis 7', 24, MUTE),
                      M('every result, chart and machine-code listing is on the site', 24, INK)).arrange(DOWN, buff=0.3)
        self.say('Every result, every chart, and the machine code behind them are on the site.')
        self.play(FadeIn(spec, shift=UP * 0.2)); self.hold(1.5); self.play(FadeOut(spec))

SCENES = ['A1Hook', 'A2Machine', 'A3Loop', 'A3Net11', 'A4Gap', 'A4Outage', 'A4Load', 'A4Surprises', 'A5Deploy', 'A5End']
