# -*- coding: utf-8 -*-
"""
Animation (ManimCE) — "The Story of TSP Algorithms".

Visually describes the performance and behavior of each algorithm across different
instance sizes (5 -> 100 cities).

Aggregated data extracted and verified from "Comparação New-Algo TSPs.xlsx".
Render:  python -m manim -qh anim_tsp.py TSPStory --media_dir analise_tsp/animacao
"""
import numpy as np
from manim import *

# ---------------------------------------------------------------- dados
ALGOS = ["LKH3", "ILS", "ALNS", "HGS", "GNN"]
SIZES = ["TSP5", "TSP10", "TSP20", "TSP50", "TSP100"]
CITIES = [5, 10, 20, 50, 100]

COLORS = {"LKH3": "#4C72B0", "ILS": "#55A868", "ALNS": "#8172B3",
          "HGS": "#CCB974", "GNN": "#C44E52"}
FULLNAME = {
    "LKH3": "Lin–Kernighan–Helsgaun",
    "ILS":  "Iterated Local Search",
    "ALNS": "Adaptive Large Neighborhood Search",
    "HGS":  "Hybrid Genetic Search",
    "GNN":  "Graph Neural Network",
}
GAP = {  # mean optimality gap (%) by size
    "LKH3": [0.0, 0.0, 0.0, 0.006, 0.0],
    "ILS":  [0.0, 0.0, 0.0, 0.029, 0.258],
    "ALNS": [0.0, 0.887, 1.996, 3.911, 4.251],
    "HGS":  [0.0, 0.0, 0.0, 0.0, 0.0],
    "GNN":  [0.0, 0.0, 0.0, 0.051, 1.336],
}
TIME = {  # mean time (s) by size
    "LKH3": [0.061, 0.062, 0.073, 0.102, 0.135],
    "ILS":  [0.071, 0.091, 0.553, 3.417, 8.124],
    "ALNS": [0.323, 0.338, 1.242, 5.034, 27.945],
    "HGS":  [0.067, 0.073, 0.346, 1.940, 7.432],
    "GNN":  [0.837, 1.011, 2.027, 5.276, 12.030],
}
WIN = {"LKH3": 99, "ILS": 89, "ALNS": 49, "HGS": 100, "GNN": 79}
RANK_COST = {"HGS": 2.580, "LKH3": 2.600, "ILS": 2.765, "GNN": 3.055, "ALNS": 4.000}

BG = "#0e1117"


class TSPStory(Scene):
    def construct(self):
        self.camera.background_color = BG
        self._intro()
        self._contenders()
        self._quality()
        self._time()
        self._tradeoff()
        self._verdict()
        self._podium()

    # utils
    def clear_all(self, run_time=0.6):
        if self.mobjects:
            self.play(*[FadeOut(m) for m in self.mobjects], run_time=run_time)

    def title(self, txt, color=WHITE):
        t = Text(txt, font_size=40, weight=BOLD, color=color)
        t.to_edge(UP, buff=0.45)
        line = Line(LEFT, RIGHT, color=GREY_B).set_width(config.frame_width - 2)
        line.next_to(t, DOWN, buff=0.18)
        return VGroup(t, line)

    def legend(self, font_size=24):
        rows = VGroup()
        for a in ALGOS:
            dot = Dot(color=COLORS[a], radius=0.11)
            lbl = Text(a, font_size=font_size, color=COLORS[a], weight=BOLD)
            rows.add(VGroup(dot, lbl).arrange(RIGHT, buff=0.18))
        rows.arrange(DOWN, aligned_edge=LEFT, buff=0.22)
        return rows

    def x_cat_labels(self, axes, ymin):
        grp = VGroup()
        for i, s in enumerate(SIZES):
            t = Text(s, font_size=22, color=GREY_A)
            t.next_to(axes.c2p(i, ymin), DOWN, buff=0.22)
            grp.add(t)
        return grp

    def y_ticklabels(self, axes, ticks, texts, xpos=0):
        grp = VGroup()
        for v, txt in zip(ticks, texts):
            t = Text(txt, font_size=22, color=GREY_A)
            t.next_to(axes.c2p(xpos, v), LEFT, buff=0.22)
            grp.add(t)
        return grp

    def framed_axes(self, x_range, y_range, x_length, y_length):
        """Axes with hidden internal lines + L-frame at minimum corner."""
        axes = Axes(x_range=x_range, y_range=y_range,
                    x_length=x_length, y_length=y_length,
                    axis_config={"include_ticks": False, "stroke_opacity": 0},
                    tips=False)
        xmin, xmax = x_range[0], x_range[1]
        ymin, ymax = y_range[0], y_range[1]
        bottom = Line(axes.c2p(xmin, ymin), axes.c2p(xmax, ymin),
                      color=GREY_B, stroke_width=2.5)
        left = Line(axes.c2p(xmin, ymin), axes.c2p(xmin, ymax),
                    color=GREY_B, stroke_width=2.5)
        return axes, VGroup(bottom, left)

    def inner_legend(self, algos=ALGOS, font_size=22):
        rows = VGroup()
        for a in algos:
            dot = Dot(color=COLORS[a], radius=0.085)
            lbl = Text(a, font_size=font_size, color=COLORS[a], weight=BOLD)
            rows.add(VGroup(dot, lbl).arrange(RIGHT, buff=0.15))
        rows.arrange(DOWN, aligned_edge=LEFT, buff=0.15)
        box = SurroundingRectangle(rows, buff=0.2, corner_radius=0.1)
        box.set_stroke(GREY_D, 1.5).set_fill(BG, opacity=0.75)
        return VGroup(box, rows)

    # 1. intro
    def _intro(self):
        title = Text("Routrip Project", font_size=54, weight=BOLD)
        sub = Text("Which algorithm is best for the application?",
                   font_size=30, color=GREY_A)
        sub.next_to(title, DOWN, buff=0.3)
        self.play(Write(title), run_time=1.8)
        self.play(FadeIn(sub, shift=UP * 0.3), run_time=1.0)
        self.wait(1.4)
        self.play(VGroup(title, sub).animate.scale(0.6).to_edge(UP, buff=0.4),
                  run_time=0.9)

        # mini city tour
        rng = np.random.default_rng(7)
        pts = [np.array([x, y, 0]) for x, y in
               rng.uniform(-3, 3, size=(9, 2)) * np.array([1.4, 0.9])]
        dots = VGroup(*[Dot(p, color=YELLOW, radius=0.09) for p in pts])
        dots.shift(DOWN * 0.4)
        self.play(LaggedStart(*[GrowFromCenter(d) for d in dots],
                              lag_ratio=0.15), run_time=2.0)
        order = list(range(9)) + [0]
        path = VMobject(color=BLUE_C, stroke_width=4)
        path.set_points_as_corners([dots[i].get_center() for i in order])
        self.play(Create(path), run_time=2.6)
        self.wait(0.8)

        premise = Text("5 algorithms · 5 sizes · 20 seeds each",
                        font_size=30, color=WHITE)
        premise.to_edge(DOWN, buff=0.7)
        self.play(FadeIn(premise, shift=UP * 0.3), run_time=1.0)
        self.wait(3.4)
        self.clear_all()

    # 2. contenders
    def _contenders(self):
        head = self.title("The Algorithms")
        self.play(FadeIn(head), run_time=0.6)

        cards = VGroup()
        for a in ALGOS:
            box = RoundedRectangle(corner_radius=0.15, width=10.2, height=0.95,
                                   stroke_color=COLORS[a], stroke_width=3,
                                   fill_color=COLORS[a], fill_opacity=0.10)
            tag = Text(a, font_size=34, weight=BOLD, color=COLORS[a])
            tag.move_to(box.get_left() + RIGHT * 1.4)
            name = Text(FULLNAME[a], font_size=28, color=WHITE)
            name.next_to(tag, RIGHT, buff=0.7)
            cards.add(VGroup(box, tag, name))
        cards.arrange(DOWN, buff=0.28).next_to(head, DOWN, buff=0.5)

        self.play(LaggedStart(*[FadeIn(c, shift=RIGHT * 0.5) for c in cards],
                              lag_ratio=0.25), run_time=2.8)
        self.wait(2.4)
        self.clear_all()

    # 3. quality
    def _quality(self):
        head = self.title("Solution Quality", color="#CFC98A")
        self.play(FadeIn(head), run_time=0.6)

        axes, frame = self.framed_axes([0, 4, 1], [0, 4.6, 1], 8.8, 4.6)
        plot = VGroup(axes, frame).move_to([0.6, -0.15, 0])
        xcats = self.x_cat_labels(axes, 0)
        yticks = self.y_ticklabels(axes, [0, 1, 2, 3, 4],
                                   ["0", "1", "2", "3", "4"])
        ylab = Text("Optimality Gap (%)",
                    font_size=22, color=GREY_A).rotate(PI / 2)
        ylab.next_to(yticks, LEFT, buff=0.2)
        draw_order = ["HGS", "LKH3", "ILS", "GNN", "ALNS"]
        leg = self.inner_legend(algos=draw_order)
        leg.move_to(axes.c2p(0.65, 3.55))
        self.play(Create(frame), FadeIn(xcats), FadeIn(yticks),
                  FadeIn(ylab), run_time=1.2)
        self.play(FadeIn(leg), run_time=0.6)
        self.wait(0.6)

        cap = Text("On small instances, algorithms perform identically.",
                   font_size=26, color=GREY_A).to_edge(DOWN, buff=0.45)
        self.play(FadeIn(cap), run_time=0.8)

        graphs = {}
        for a in ALGOS:
            graphs[a] = axes.plot_line_graph(
                x_values=list(range(5)), y_values=GAP[a],
                line_color=COLORS[a], add_vertex_dots=True,
                vertex_dot_radius=0.055, stroke_width=5)
        for a in draw_order:
            self.play(Create(graphs[a]), run_time=1.3)
        self.wait(2.0)

        self.play(FadeOut(cap), run_time=0.4)
        cap2 = Text("As instances grow, differences emerge", font_size=25, color=WHITE)
        cap2.to_edge(DOWN, buff=0.45)
        self.play(FadeIn(cap2), run_time=0.8)
        self.play(Indicate(graphs["ALNS"], color=COLORS["ALNS"]),
                  run_time=1.4)
        self.play(Indicate(graphs["GNN"], color=COLORS["GNN"]),
                  run_time=1.2)
        self.wait(0.5)
        self.play(FadeOut(cap2), run_time=0.4)
        star = Text("HGS and LKH3 remain statistically near-optimal", font_size=25,
                    color=COLORS["HGS"], weight=BOLD).to_edge(DOWN, buff=0.45)
        self.play(FadeIn(star), Indicate(graphs["HGS"], color=COLORS["HGS"]),
                  run_time=1.4)
        self.wait(3.8)
        self.clear_all()

    # 4. time
    def _time(self):
        head = self.title("Execution Speed", color="#8FB3E0")
        self.play(FadeIn(head), run_time=0.6)

        def L(v):
            return float(np.log10(v))

        axes, frame = self.framed_axes([0, 4, 1], [-1.4, 1.6, 1], 8.8, 4.6)
        plot = VGroup(axes, frame).move_to([0.6, -0.15, 0])
        xcats = self.x_cat_labels(axes, -1.4)
        yticks = self.y_ticklabels(axes, [-1, 0, 1], ["0.1 s", "1 s", "10 s"])
        ylab = Text("Time (s, log scale)",
                    font_size=22, color=GREY_A).rotate(PI / 2)
        ylab.next_to(yticks, LEFT, buff=0.2)
        leg = self.inner_legend()
        leg.move_to(axes.c2p(0.6, 1.0))
        self.play(Create(frame), FadeIn(xcats), FadeIn(yticks),
                  FadeIn(ylab), run_time=1.2)
        self.play(FadeIn(leg), run_time=0.6)
        self.wait(0.5)

        graphs = {}
        for a in ALGOS:
            graphs[a] = axes.plot_line_graph(
                x_values=list(range(5)), y_values=[L(v) for v in TIME[a]],
                line_color=COLORS[a], add_vertex_dots=True,
                vertex_dot_radius=0.055, stroke_width=5)
            self.play(Create(graphs[a]), run_time=1.2)

        cap = Text("LKH3 shows very small scaling growth.",
                   font_size=26, color=COLORS["LKH3"]).to_edge(DOWN, buff=0.45)
        self.play(FadeIn(cap), run_time=0.8)
        self.play(Indicate(graphs["LKH3"], color=COLORS["LKH3"]), run_time=1.4)
        self.wait(1.2)
        self.play(FadeOut(cap), run_time=0.3)
        cap2 = Text("ALNS reaches ~28 s on TSP100, showing poorest scaling.",
                    font_size=26, color=COLORS["ALNS"]).to_edge(DOWN, buff=0.45)
        self.play(FadeIn(cap2), Indicate(graphs["ALNS"], color=COLORS["ALNS"]),
                  run_time=1.6)
        self.wait(3.6)
        self.clear_all()

    # 5. trade-off
    def _tradeoff(self):
        head = self.title("Quality vs Time Trade-off (TSP100)")
        self.play(FadeIn(head), run_time=0.6)

        def L(v):
            return float(np.log10(v))

        axes, frame = self.framed_axes([-1.1, 1.6, 1], [0, 4.7, 1], 9.0, 4.5)
        plot = VGroup(axes, frame).move_to([0.55, -0.25, 0])
        ylab = Text("Gap (%)", font_size=22,
                    color=GREY_A).rotate(PI / 2)
        xt = VGroup()
        for v, txt in [(-1, "0.1 s"), (0, "1 s"), (1, "10 s")]:
            t = Text(txt, font_size=22, color=GREY_A)
            t.next_to(axes.c2p(v, 0), DOWN, buff=0.2)
            xt.add(t)
        yt = self.y_ticklabels(axes, [0, 1, 2, 3, 4],
                               ["0", "1", "2", "3", "4"], xpos=-1.1)
        ylab.next_to(yt, LEFT, buff=0.2)
        xlab = Text("Time (s, log scale)",
                    font_size=22, color=GREY_A)
        xlab.next_to(xt, DOWN, buff=0.25)
        self.play(Create(frame), FadeIn(xlab), FadeIn(ylab), FadeIn(xt),
                  FadeIn(yt), run_time=1.2)

        # Labels positioned to avoid collision (HGS lower-left, ILS upper)
        lbl_dir = {"LKH3": UP, "HGS": DOWN + LEFT, "ILS": UP,
                   "GNN": RIGHT, "ALNS": UP}
        dots, labels = {}, {}
        for a in ALGOS:
            p = axes.c2p(L(TIME[a][-1]), GAP[a][-1])
            d = Dot(p, color=COLORS[a], radius=0.13).set_stroke(WHITE, 2)
            lbl = Text(a, font_size=23, weight=BOLD, color=COLORS[a])
            lbl.next_to(d, lbl_dir[a], buff=0.12)
            dots[a] = d
            labels[a] = lbl
        self.play(LaggedStart(*[GrowFromCenter(dots[a]) for a in ALGOS],
                              lag_ratio=0.25),
                  *[FadeIn(labels[a]) for a in ALGOS], run_time=2.2)
        self.wait(1.6)

        # Dominated algorithms in upper area
        dom = Text("GNN and ALNS show slower execution.",
                   font_size=25, color=WHITE)
        dom.next_to(head, DOWN, buff=0.35).shift(LEFT * 0.2)
        self.play(FadeIn(dom),
                  Indicate(dots["ALNS"], color=COLORS["ALNS"], scale_factor=1.4),
                  Indicate(dots["GNN"], color=COLORS["GNN"], scale_factor=1.4),
                  run_time=1.6)
        self.wait(1.8)

        # Pareto frontier (LKH3 and HGS are non-dominated)
        pf = DashedLine(dots["LKH3"].get_center(), dots["HGS"].get_center(),
                        color=GREEN_B, stroke_width=3)
        pflab = Text("Pareto Frontier", font_size=22, color=GREEN_B)
        pflab.move_to(axes.c2p(-0.15, 0.55))
        self.play(Create(pf), FadeIn(pflab), run_time=1.4)

        sweet = Text("LKH3 at the sweet spot:\nfast and near-optimal.",
                     font_size=26, color=COLORS["LKH3"], weight=BOLD,
                     line_spacing=0.9)
        if sweet.width > 4.2:
            sweet.scale_to_fit_width(4.2)
        sweet.move_to(axes.c2p(-0.35, 3.2))
        self.play(FadeIn(sweet), Flash(dots["LKH3"], color=COLORS["LKH3"],
                                       flash_radius=0.4), run_time=1.4)
        self.wait(4.0)
        self.clear_all()

    # 6. verdict
    def _verdict(self):
        head = self.title("The Verdict")
        self.play(FadeIn(head), run_time=0.6)

        sub = Text("Win rate (achieved best solution)",
                   font_size=26, color=GREY_A)
        sub.next_to(head, DOWN, buff=0.35)
        self.play(FadeIn(sub), run_time=0.6)

        # Proportional bars
        ordered = sorted(ALGOS, key=lambda a: WIN[a], reverse=True)
        max_w = 6.0
        bars = VGroup()
        for a in ordered:
            bars.add(Rectangle(width=max_w * WIN[a] / 100, height=0.42,
                               fill_color=COLORS[a], fill_opacity=0.9,
                               stroke_width=0))
        bars.arrange(DOWN, buff=0.28, aligned_edge=LEFT)

        rowgrps = VGroup()
        for bar, a in zip(bars, ordered):
            tag = Text(a, font_size=24, weight=BOLD, color=COLORS[a])
            tag.next_to(bar, LEFT, buff=0.3)
            val = Text(f"{WIN[a]}%", font_size=22, color=GREY_A)
            val.next_to(bar, RIGHT, buff=0.2)
            rowgrps.add(VGroup(tag, bar, val))
        rowgrps.next_to(sub, DOWN, buff=0.45).set_x(0.3)

        for r in rowgrps:
            self.play(FadeIn(r[0]), GrowFromEdge(r[1], LEFT), FadeIn(r[2]),
                      run_time=0.6)
        self.wait(1.2)

        note = Text("HGS and LKH3 are nearly tied at the top",
                    font_size=24, color=GREY_A)
        note.next_to(rowgrps, DOWN, buff=0.5)
        self.play(FadeIn(note), run_time=0.8)
        self.wait(2.8)
        self.clear_all()

    # 7. podium
    def _podium(self):
        head = self.title("Final Verdict")
        self.play(FadeIn(head), run_time=0.6)

        def card(algo, title, detail, accent):
            box = RoundedRectangle(corner_radius=0.18, width=11, height=1.5,
                                   stroke_color=COLORS[algo], stroke_width=4,
                                   fill_color=COLORS[algo], fill_opacity=0.12)
            badge = Text(title, font_size=24, weight=BOLD, color=accent)
            name = Text(algo, font_size=38, weight=BOLD, color=COLORS[algo])
            left = VGroup(badge, name).arrange(DOWN, buff=0.12, aligned_edge=LEFT)
            left_w = box.width * 0.42
            if left.width > left_w:
                left.scale_to_fit_width(left_w)
            left.next_to(box.get_left(), RIGHT, buff=0.5)
            det = Text(detail, font_size=24, color=WHITE)
            right_w = box.width * 0.44
            if det.width > right_w:
                det.scale_to_fit_width(right_w)
            det.next_to(box.get_right(), LEFT, buff=0.5)
            return VGroup(box, left, det)

        c1 = card("HGS", "Best Quality", "Achieves optimal · 100% win rate",
                  "#FFD54A")
        c2 = card("LKH3", "Best Overall Algorithm",
                  "Near-optimal in nearly all cases and extremely fast", "#FFD54A")
        c3 = card("ALNS", "Poorest Performance", "Highest gap · poorest scalability",
                  "#FF6B6B")
        cards = VGroup(c1, c2, c3).arrange(DOWN, buff=0.35)
        cards.next_to(head, DOWN, buff=0.5)

        for c in cards:
            self.play(FadeIn(c, shift=UP * 0.3), run_time=1.0)
            self.wait(0.9)

        foot = Text("GNN: shows promise, but lacks performance on small instances.",
                    font_size=25, color=COLORS["GNN"])
        foot.next_to(cards, DOWN, buff=0.4)
        self.play(FadeIn(foot), run_time=1.0)
        self.wait(3.0)

        self.play(*[FadeOut(m) for m in self.mobjects], run_time=0.8)
        end = Text("For this application: LKH3 is the default choice.",
                   font_size=34, weight=BOLD, color=WHITE)
        self.play(Write(end), run_time=2.0)
        self.wait(3.4)
        self.play(FadeOut(end), run_time=1.2)
