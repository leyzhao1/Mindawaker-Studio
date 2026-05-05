from manim import *
import numpy as np

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

MARK_COLOR = YELLOW_C
EXP_COLOR = GREEN
LOGI_COLOR = ORANGE
LIMIT_COLOR = RED
BAR_COLOR = BLUE_D


class LogisticGrowthStory(Scene):
    def construct(self):
        self.camera.background_color = BG_COLOR
        self.header = None

        self.show_title()
        self.act1_review_exponential()
        self.act2_resource_limit()
        self.act3_verhulst_formula()
        self.act4_s_curve()
        self.act5_real_examples()
        self.ending()

    def switch_header(self, text):
        self.header = switch_header(self, self.header, text, size=30, color=TITLE_COLOR, run_time=0.6)

    def show_title(self):
        play_title_card(
            self,
            title="Why Doesn't Exponential Growth Continue Forever?",
            subtitle="The Logistic Model: From Unlimited Explosion to Eventual Balance",
            title_size=38,
            subtitle_size=26,
            title_color=TITLE_COLOR,
            subtitle_color=SUB_COLOR,
            hold_time=1.5,
        )

    def act1_review_exponential(self):
        self.switch_header("11. The Logistic Model: From Unlimited Explosion to Eventual Balance")

        note = en_subtitle(
            "Last time we saw that if every individual keeps reproducing, the population grows rapidly.",
            24, TEXT_COLOR
        ).next_to(self.header, DOWN, buff=0.25)

        axes = Axes(
            x_range=[0, 6, 1],
            y_range=[0, 40, 10],
            x_length=8,
            y_length=4.5,
            axis_config={"color": GRAY_A},
            tips=False
        ).shift(DOWN * 0.4)

        x_label = en_text("Time", 22, BAR_COLOR).next_to(axes.x_axis, RIGHT, buff=0.2)
        y_label = en_text("Quantity", 22, BAR_COLOR).next_to(axes.y_axis, UP, buff=0.2)

        exp_graph = axes.plot(lambda x: 2**x, x_range=[0, 5.2], color=EXP_COLOR)
        exp_formula = MathTex("N(t)=N_0e^{rt}", color=HIGHLIGHT_COLOR).scale(1.0).to_corner(UR).shift(LEFT + DOWN)

        question = en_text(
            "But in reality, no population can grow like this forever.",
            26, HIGHLIGHT_COLOR
        ).to_edge(DOWN)

        self.play(FadeIn(note), Create(axes), FadeIn(x_label), FadeIn(y_label), run_time=1.0)
        self.play(Create(exp_graph), Write(exp_formula), run_time=1.6)
        self.play(FadeIn(question), run_time=0.8)
        self.wait(1.6)

        self.play(
            FadeOut(note), FadeOut(question),
            FadeOut(exp_graph), FadeOut(exp_formula),
            FadeOut(x_label), FadeOut(y_label), FadeOut(axes),
            run_time=0.9
        )

    def act2_resource_limit(self):
        self.switch_header("12. Resources Limit Growth")

        note = en_text(
            "Space, food, and competition all make further growth harder and harder.",
            24, TEXT_COLOR
        ).next_to(self.header, DOWN, buff=0.25)

        self.play(FadeIn(note), run_time=0.6)

        small_circle = Circle(radius=1.1, color=BLUE).shift(LEFT * 3 + DOWN * 0.2)
        small_label = en_text("Small population", 24, BLUE).next_to(small_circle, UP, buff=0.25)

        small_dots = VGroup(*[
            Dot(
                point=small_circle.get_center() + np.array([
                    np.random.uniform(-0.6, 0.6),
                    np.random.uniform(-0.6, 0.6),
                    0,
                ]),
                radius=0.05,
                color=BLUE_C,
            )
            for _ in range(8)
        ])

        small_text = en_text("Abundant Resources\nRapid Growth", 22, TEXT_COLOR, line_spacing=0.8).next_to(small_circle, DOWN, buff=0.3)

        big_circle = Circle(radius=1.1, color=ORANGE).shift(RIGHT * 3 + DOWN * 0.2)
        big_label = en_text("Large population", 24, ORANGE).next_to(big_circle, UP, buff=0.25)

        big_dots = VGroup(*[
            Dot(
                point=big_circle.get_center() + np.array([
                    np.random.uniform(-0.75, 0.75),
                    np.random.uniform(-0.75, 0.75),
                    0,
                ]),
                radius=0.05,
                color=ORANGE,
            )
            for _ in range(28)
        ])

        big_text = en_text("Resource shortages\nSlower growth", 22, TEXT_COLOR, line_spacing=0.8).next_to(big_circle, DOWN, buff=0.3)

        self.play(
            FadeIn(small_circle), FadeIn(big_circle),
            FadeIn(small_label), FadeIn(big_label),
            run_time=0.8,
        )
        self.play(
            LaggedStart(*[FadeIn(d, scale=0.6) for d in small_dots], lag_ratio=0.06),
            LaggedStart(*[FadeIn(d, scale=0.6) for d in big_dots], lag_ratio=0.02),
            run_time=1.2,
        )
        self.play(FadeIn(small_text), FadeIn(big_text), run_time=0.7)

        remark = en_text(
            "The closer a population gets to the environmental limit, the slower it grows.",
            24, HIGHLIGHT_COLOR,
        ).to_edge(DOWN)

        self.play(FadeIn(remark), run_time=0.7)
        self.wait(1.8)

        self.play(
            FadeOut(note), FadeOut(remark),
            FadeOut(small_circle), FadeOut(big_circle),
            FadeOut(small_label), FadeOut(big_label),
            FadeOut(small_dots), FadeOut(big_dots),
            FadeOut(small_text), FadeOut(big_text),
            run_time=0.9,
        )

    def act3_verhulst_formula(self):
        self.switch_header("13. A Mathematician's Revision")

        intro = en_subtitle(
            "In 1838, Verhulst proposed that the rate of growth depends not only on the quantity itself, but also on how far away from the \"upper limit\".",
            24, TEXT_COLOR, line_spacing=0.8,
        ).next_to(self.header, DOWN, buff=0.25)

        formula = MathTex(
            r"\frac{dN}{dt}=rN\left(1-\frac{N}{K}\right)",
            color=FORMULA_COLOR,
        ).scale(1.2).shift(UP * 0.6)

        explain1 = MathTex("r", color=YELLOW).scale(1.0)
        explain1_text = en_text("growth rate", 24, TEXT_COLOR)
        explain1_group = VGroup(explain1, explain1_text).arrange(RIGHT, buff=0.15)

        explain2 = MathTex("N", color=GREEN).scale(1.0)
        explain2_text = en_text("current population", 24, TEXT_COLOR)
        explain2_group = VGroup(explain2, explain2_text).arrange(RIGHT, buff=0.15)

        explain3 = MathTex("K", color=ORANGE).scale(1.0)
        explain3_text = en_text("carrying capacity", 24, TEXT_COLOR)
        explain3_group = VGroup(explain3, explain3_text).arrange(RIGHT, buff=0.15)

        explains = VGroup(explain1_group, explain2_group, explain3_group)
        explains.arrange(DOWN, aligned_edge=LEFT, buff=0.3).shift(DOWN)

        self.play(FadeIn(intro), run_time=0.8)
        self.play(Write(formula), run_time=1.4)
        self.play(FadeIn(explains), run_time=0.8)

        focus = MathTex(
            r"1-\frac{N}{K}",
            color=HIGHLIGHT_COLOR,
        ).scale(1.2).to_edge(RIGHT).shift(UP * 0.6)
        focus_text = en_subtitle(
            "This factor represents how much room for growth is still left.",
            24, MARK_COLOR, width=20,
        ).next_to(focus, DOWN, buff=0.25)

        self.play(Write(focus), FadeIn(focus_text), run_time=1.0)
        self.wait(1.5)

        remark = en_subtitle(
            "When N is small, this factor is close to 1. When N approaches K, this factor approaches 0.",
            24, HIGHLIGHT_COLOR,
        ).to_edge(DOWN)

        self.play(FadeIn(remark), run_time=0.8)
        self.wait(1.8)

        self.play(
            FadeOut(intro), FadeOut(formula), FadeOut(explains),
            FadeOut(focus), FadeOut(focus_text), FadeOut(remark),
            run_time=0.9,
        )

    def act4_s_curve(self):
        self.switch_header("14. The S-Shaped Curve Appears")

        note = en_subtitle(
            "It started with exponential growth, then gradually slowed down, and finally stabilized...",
            22, TEXT_COLOR,
        ).next_to(self.header, DOWN, buff=0.25)

        axes = Axes(
            x_range=[0, 10, 1],
            y_range=[0, 12, 2],
            x_length=8,
            y_length=4.8,
            axis_config={"color": GRAY_A},
            tips=False,
        ).shift(DOWN * 0.45)

        x_label = en_text("Time", 22, BAR_COLOR).next_to(axes.x_axis, RIGHT, buff=0.2)
        y_label = en_text("Population", 22, BAR_COLOR).next_to(axes.y_axis, UP, buff=0.2)

        K = 10
        logistic_graph = axes.plot(
            lambda x: K / (1 + 9 * np.exp(-0.9 * x)),
            x_range=[0, 10],
            color=LOGI_COLOR,
        )

        exp_like_graph = axes.plot(
            lambda x: 0.8 * np.exp(0.42 * x),
            x_range=[0, 6],
            color=EXP_COLOR,
        )

        limit_line = DashedLine(
            axes.c2p(0, K),
            axes.c2p(10, K),
            color=LIMIT_COLOR,
        )
        limit_label = MathTex("K", color=LIMIT_COLOR).next_to(limit_line, RIGHT, buff=0.15)

        logistic_formula = MathTex(
            r"N(t)=\frac{K}{1+A e^{-rt}}",
            color=HIGHLIGHT_COLOR,
        ).scale(1.0).to_edge(RIGHT).shift(UP * 0.3)

        self.play(FadeIn(note), Create(axes), FadeIn(x_label), FadeIn(y_label), run_time=1.0)
        self.play(Create(exp_like_graph), run_time=1.1)
        self.wait(0.6)

        transform_text = en_text("But the real world gradually runs into limits.", 24, HIGHLIGHT_COLOR).to_edge(DOWN)
        self.play(FadeIn(transform_text), run_time=0.7)

        self.play(
            FadeOut(exp_like_graph),
            Create(logistic_graph),
            Create(limit_line),
            FadeIn(limit_label),
            Write(logistic_formula),
            run_time=1.8,
        )

        self.wait(1.8)

        self.play(
            FadeOut(note), FadeOut(transform_text),
            FadeOut(logistic_graph), FadeOut(limit_line), FadeOut(limit_label),
            FadeOut(logistic_formula),
            FadeOut(x_label), FadeOut(y_label), FadeOut(axes),
            run_time=0.9,
        )

    def act5_real_examples(self):
        self.switch_header("15. S-Curves in the Real World")

        note = en_subtitle(
            "Many growth processes begin rapidly, then slow down, and finally approach saturation.",
            22, TEXT_COLOR,
        ).next_to(self.header, DOWN, buff=0.25)

        box1 = RoundedRectangle(corner_radius=0.2, width=4.3, height=3.1, color=BLUE)
        box2 = RoundedRectangle(corner_radius=0.2, width=4.3, height=3.1, color=GREEN)
        box3 = RoundedRectangle(corner_radius=0.2, width=4.3, height=3.1, color=ORANGE)

        boxes = VGroup(box1, box2, box3).arrange(RIGHT, buff=0.45).shift(DOWN * 0.5)

        title1 = en_text("Bacterial Culture", 24, BLUE).move_to(box1.get_top() + DOWN * 0.35)
        title2 = en_text("Urban Population", 24, GREEN).move_to(box2.get_top() + DOWN * 0.35)
        title3 = en_text("Technology Adoption", 24, ORANGE).move_to(box3.get_top() + DOWN * 0.35)

        content1 = en_subtitle("Petri dish space is limited\nit will not grow indefinitely.", 21, TEXT_COLOR, width=20, line_spacing=0.75).move_to(box1.get_center() + DOWN * 0.05)
        content2 = en_subtitle("Urban development is constrained\n by resources and the environment.", 21, TEXT_COLOR, width=20, line_spacing=0.75).move_to(box2.get_center() + DOWN * 0.05)
        content3 = en_subtitle("Product user growth often \nfollows an S-curve.", 21, TEXT_COLOR, width=20, line_spacing=0.75).move_to(box3.get_center() + DOWN * 0.05)

        self.play(FadeIn(note), run_time=0.6)
        self.play(
            LaggedStart(
                FadeIn(box1, shift=UP * 0.2),
                FadeIn(box2, shift=UP * 0.2),
                FadeIn(box3, shift=UP * 0.2),
                lag_ratio=0.2,
            ),
            run_time=1.0,
        )
        self.play(
            FadeIn(title1), FadeIn(title2), FadeIn(title3),
            FadeIn(content1), FadeIn(content2), FadeIn(content3),
            run_time=0.8,
        )

        remark = en_subtitle(
            "Exponential growth describes an ideal explosion, while the logistic model is closer to the real world.",
            24, HIGHLIGHT_COLOR,
        ).to_edge(DOWN)

        self.play(FadeIn(remark), run_time=0.7)
        self.wait(1.8)

        self.play(
            FadeOut(note), FadeOut(remark),
            FadeOut(boxes),
            FadeOut(title1), FadeOut(title2), FadeOut(title3),
            FadeOut(content1), FadeOut(content2), FadeOut(content3),
            run_time=0.9,
        )

    def ending(self):
        self.switch_header("Conclusion")

        summary_lines = [
            "Exponential growth tells us that quantities can explode rapidly.",
            "The logistic model reminds us that the real world always has limits.",
            "When growth meets constraints, the curve moves from explosion toward balance.",
        ]
        play_summary_scene(
            self,
            summary_lines=summary_lines,
            line_size=26,
            line_color=TEXT_COLOR,
            highlight_last=True,
            highlight_color=HIGHLIGHT_COLOR,
            formula_tex=r"\frac{dN}{dt}=rN\left(1-\frac{N}{K}\right)",
            formula_color=LOGI_COLOR,
            formula_scale=1.1,
            footer_text="Next time, we can continue with rabbits and foxes: why do their numbers chase each other in cycles?",
            footer_size=22,
            footer_color=SUB_COLOR,
            footer_as_subtitle=True,
        )
        fade_out_all(self, run_time=1.0)
