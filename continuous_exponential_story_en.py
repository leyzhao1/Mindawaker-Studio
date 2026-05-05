from manim import *
import numpy as np
import textwrap

from app.utils.render_primitives import (
    BG_COLOR,
    TITLE_COLOR,
    SUB_COLOR,
    TEXT_COLOR,
    FORMULA_COLOR,
    HIGHLIGHT_COLOR,
    en_text,
    en_subtitle,
    fade_out_all,
    switch_header,
)
from app.utils.story_blocks import play_title_card, play_summary_scene

DISCRETE_COLOR = GREEN
CONTINUOUS_COLOR = ORANGE
CURVE_COLOR = TEAL
LIMIT_COLOR = RED


class ContinuousExponentialStory(Scene):
    def construct(self):
        self.camera.background_color = BG_COLOR
        self.header = None

        self.show_title()
        self.act1_discrete_doubling()
        self.act2_continuous_reproduction()
        self.act3_diff_equation()
        self.act4_why_e_appears()
        self.act5_curve_and_summary()
        self.ending()

    def switch_header(self, text):
        self.header = switch_header(self, self.header, text, size=30, color=TITLE_COLOR, run_time=0.6)

    def show_title(self):
        play_title_card(
            self,
            title="Continuous Reproduction Eventually Gives: e^{rt}",
            subtitle="A Math Story from Discrete Doubling to Continuous Growth",
            title_size=38,
            subtitle_size=26,
            title_color=TITLE_COLOR,
            subtitle_color=SUB_COLOR,
            hold_time=1.5,
        )

    def act1_discrete_doubling(self):
        self.switch_header("6. If Reproduction Happens by Generations")

        note = en_text(
            "Suppose the population doubles every generation.",
            24, TEXT_COLOR,
        ).next_to(self.header, DOWN, buff=0.25)

        self.play(FadeIn(note), run_time=0.6)

        nums = [1, 2, 4, 8, 16, 32]
        num_mobs = VGroup(*[
            en_text(str(n), 30, DISCRETE_COLOR) for n in nums
        ])
        num_mobs.arrange(RIGHT, buff=0.45).shift(UP * 0.8)

        arrows = VGroup()
        for i in range(len(nums) - 1):
            arr = Arrow(
                start=num_mobs[i].get_right() + RIGHT * 0.1,
                end=num_mobs[i + 1].get_left() + LEFT * 0.1,
                buff=0.05,
                stroke_width=3,
                color=GRAY_B,
            )
            arrows.add(arr)

        remark = en_text(
            "This is natural, because each generation multiplies by 2.",
            24, HIGHLIGHT_COLOR,
        ).next_to(num_mobs, DOWN, buff=1)

        bottom_formula = MathTex(
            r"N_n = N_0 \cdot 2^n",
            color=FORMULA_COLOR,
        ).scale(1.2).next_to(remark, DOWN, buff=0.35)

        self.play(LaggedStart(*[FadeIn(n, shift=UP * 0.15) for n in num_mobs], lag_ratio=0.12), run_time=1.3)
        self.play(LaggedStart(*[GrowArrow(a) for a in arrows], lag_ratio=0.1), run_time=1.0)
        self.play(Write(bottom_formula), FadeIn(remark), run_time=1.0)
        self.wait(1.6)

        question = en_subtitle(
            "But in the real world, reproduction does not happen in neat, synchronized generations.",
            24, TEXT_COLOR, width=85,
        ).to_edge(DOWN)

        self.play(
            FadeOut(remark),
            FadeOut(bottom_formula),
            FadeIn(question),
            run_time=0.8,
        )
        self.wait(1.5)

        self.play(
            FadeOut(note), FadeOut(question),
            FadeOut(num_mobs), FadeOut(arrows),
            run_time=0.9,
        )

    def act2_continuous_reproduction(self):
        self.switch_header("7. In Reality, Reproduction Is More Continuous")

        note = en_subtitle(
            "\n".join(textwrap.wrap("Bacteria do not wait for a bell to ring before they all divide together. They reproduce continuously over time.", 80)),
            24, TEXT_COLOR, width=85,
        ).next_to(self.header, DOWN, buff=0.25)

        self.play(FadeIn(note), run_time=0.7)

        timeline = NumberLine(
            x_range=[0, 5, 1],
            length=8,
            include_numbers=True,
            color=GRAY_A,
        ).shift(DOWN * 1.0)

        t_label = en_text("Time", 22, TEXT_COLOR).next_to(timeline, RIGHT, buff=0.2)

        dots = VGroup(
            Dot(timeline.n2p(0.5), color=CONTINUOUS_COLOR, radius=0.06),
            Dot(timeline.n2p(1.2), color=CONTINUOUS_COLOR, radius=0.06),
            Dot(timeline.n2p(1.9), color=CONTINUOUS_COLOR, radius=0.06),
            Dot(timeline.n2p(2.7), color=CONTINUOUS_COLOR, radius=0.06),
            Dot(timeline.n2p(3.1), color=CONTINUOUS_COLOR, radius=0.06),
            Dot(timeline.n2p(4.2), color=CONTINUOUS_COLOR, radius=0.06),
        )

        events = VGroup(*[
            en_text("split", 18, CONTINUOUS_COLOR).next_to(d, UP, buff=0.12)
            for d in dots
        ])

        self.play(Create(timeline), FadeIn(t_label), run_time=1.0)
        self.play(
            LaggedStart(*[
                AnimationGroup(FadeIn(d, scale=0.6), FadeIn(e, shift=UP * 0.08))
                for d, e in zip(dots, events)
            ], lag_ratio=0.18),
            run_time=1.6,
        )

        remark = en_subtitle(
            "So growth is no longer just ‘times 2 each generation’; instead, at every moment it continues according to the current population size.",
            24, HIGHLIGHT_COLOR, width=85,
        ).to_edge(DOWN)

        self.play(FadeIn(remark), run_time=0.8)
        self.wait(1.8)

        self.play(
            FadeOut(note), FadeOut(remark),
            FadeOut(timeline), FadeOut(t_label),
            FadeOut(dots), FadeOut(events),
            run_time=0.9,
        )

    def act3_diff_equation(self):
        self.switch_header("8. Growth Rate Is Proportional to Current Population")

        note = en_subtitle(
            "If there are more individuals, then more individuals can reproduce, so the growth rate should be proportional to the current population.",
            24, TEXT_COLOR, width=85,
        ).next_to(self.header, DOWN, buff=0.25)

        self.play(FadeIn(note), run_time=0.8)

        left_text = en_text("More individuals", 28, GREEN).shift(LEFT * 4 + UP * 0.5)
        arrow = Arrow(LEFT * 2.2 + UP * 0.5, RIGHT * 2.2 + UP * 0.5, color=GRAY_B)
        right_text = en_text("Faster growth", 28, ORANGE).shift(RIGHT * 4 + UP * 0.5)

        self.play(FadeIn(left_text), GrowArrow(arrow), FadeIn(right_text), run_time=1.0)

        formula = MathTex(
            r"\frac{dN}{dt} = rN",
            color=FORMULA_COLOR,
        ).scale(1.6).shift(DOWN * 0.4)

        formula_note = en_text(
            "This is the most basic model of exponential population growth.",
            24, HIGHLIGHT_COLOR,
        ).to_edge(DOWN)

        r_note = MathTex("r", color=YELLOW).scale(1.0)
        r_text = en_text("growth rate", 24, TEXT_COLOR)
        r_group = VGroup(r_note, r_text).arrange(RIGHT, buff=0.15)

        N_note = MathTex("N", color=GREEN).scale(1.0)
        N_text = en_text("current population", 24, TEXT_COLOR)
        N_group = VGroup(N_note, N_text).arrange(RIGHT, buff=0.15)

        explain = VGroup(r_group, N_group).arrange(DOWN, aligned_edge=LEFT, buff=0.3)
        explain.shift(DOWN * 2.1)

        self.play(Write(formula), run_time=1.2)
        self.play(FadeIn(formula_note), FadeIn(explain), run_time=0.8)
        self.wait(1.8)

        self.play(
            FadeOut(note),
            FadeOut(left_text), FadeOut(arrow), FadeOut(right_text),
            FadeOut(formula_note), FadeOut(explain),
            FadeOut(formula),
            run_time=0.9,
        )

        self.formula_main = formula

    def act4_why_e_appears(self):
        self.switch_header('9：Why does the "e" appear?')

        note = en_subtitle(
            "You can think of continuous growth like this: divide time into smaller and smaller pieces, and let the population grow a little in each piece.",
            24, TEXT_COLOR, width=85,
        ).next_to(self.header, DOWN, buff=0.25)

        self.play(FadeIn(note), run_time=0.7)

        step1 = MathTex(
            r"N(t+\Delta t) \approx N(t)+N(t)r\Delta t = N(t)\left(1+r\Delta t\right)",
            color=FORMULA_COLOR,
        ).scale(1.0).shift(UP * 1.2)

        step2 = MathTex(
            r"N(t) \approx N_0\left(1+r\Delta t\right)^{t/\Delta t}",
            color=FORMULA_COLOR,
            tex_to_color_map={r"\Delta t": HIGHLIGHT_COLOR},
        ).scale(1.0).shift(UP * 0.1)

        step3 = MathTex(
            r"\Delta t \to 0",
            color=HIGHLIGHT_COLOR,
        ).scale(1.1).shift(DOWN * 1.0)

        step4 = MathTex(
            r"N(t)=N_0 e^{rt}",
            color=CURVE_COLOR,
        ).scale(1.5).shift(DOWN * 2.1)

        self.play(Write(step1), run_time=1.3)
        self.wait(0.8)
        self.play(Write(step2), run_time=1.3)
        self.wait(0.8)
        self.play(FadeIn(step3), run_time=0.8)
        self.wait(1.0)
        self.play(Write(step4), run_time=1.2)

        remark = en_subtitle(
            "e does not appear out of nowhere. It comes from slicing the growth process into infinitely small steps.",
            24, HIGHLIGHT_COLOR, width=85,
        ).to_edge(DOWN)

        self.play(FadeIn(remark), run_time=0.8)
        self.wait(2.0)

        self.main_fomula = step4
        self.play(
            FadeOut(note), FadeOut(remark),
            FadeOut(step1), FadeOut(step2), FadeOut(step3),
            run_time=0.9,
        )

        self.final_formula = step4

    def act5_curve_and_summary(self):
        self.switch_header("10. And Then the Curve Appears")

        self.play(
            self.final_formula.animate.to_corner(UR).shift(LEFT * 0.5 + DOWN * 0.4),
            run_time=0.8,
        )

        axes = Axes(
            x_range=[0, 6, 1],
            y_range=[0, 25, 5],
            x_length=8,
            y_length=4.5,
            axis_config={"color": GRAY_A},
            tips=False,
        ).shift(DOWN * 0.4)

        x_label = en_text("Time", 22, TEXT_COLOR).next_to(axes.x_axis, RIGHT, buff=0.2)
        y_label = en_text("Quantity", 22, TEXT_COLOR).next_to(axes.y_axis, UP, buff=0.2)

        graph = axes.plot(
            lambda x: np.exp(0.6 * x),
            x_range=[0, 5.2],
            color=CURVE_COLOR,
        )

        discrete_text = en_subtitle("Discrete: doubling each generation", 22, DISCRETE_COLOR).shift(LEFT * 5.5 + UP * 2.3)
        discrete_formula = MathTex(
            r"N_n = N_0 \cdot 2^n",
            color=DISCRETE_COLOR,
        ).scale(0.9).next_to(discrete_text, DOWN, buff=0.2)

        cont_text = en_text("Continuous: growing at every moment", 24, CONTINUOUS_COLOR).shift(RIGHT * 2.4 + UP * 2)

        self.play(Create(axes), FadeIn(x_label), FadeIn(y_label), run_time=1.0)
        self.play(Create(graph), run_time=1.6)
        self.play(
            FadeIn(discrete_text), Write(discrete_formula),
            FadeIn(cont_text),
            run_time=1.0,
        )

        remark = en_text(
            "Discrete doubling gives 2^n, while continuous growth naturally leads to e^{rt}.",
            24, HIGHLIGHT_COLOR,
        ).to_edge(DOWN)

        self.play(FadeIn(remark), run_time=0.8)
        self.wait(2.0)

        self.play(
            FadeOut(remark),
            FadeOut(discrete_text), FadeOut(discrete_formula),
            FadeOut(cont_text),
            FadeOut(graph), FadeOut(x_label), FadeOut(y_label), FadeOut(axes),
            FadeOut(self.main_fomula),
            run_time=0.9,
        )

    def ending(self):
        self.switch_header("")

        play_summary_scene(
            self,
            summary_lines=[
                "If the growth rate is proportional to the current population,",
                "then the population rises along an exponential curve.",
            ],
            line_size=28,
            line_color=TEXT_COLOR,
            formula_tex=r"N(t)=N_0 e^{rt}",
            formula_color=CURVE_COLOR,
            formula_scale=1.8,
            footer_text="Next time, we will ask: why does growth in the real world not continue like this forever?",
            footer_size=22,
            footer_color=HIGHLIGHT_COLOR,
        )
        fade_out_all(self, run_time=1.0)
