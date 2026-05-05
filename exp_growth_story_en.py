from manim import *

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
)
from app.utils.story_blocks import (
    play_title_card,
    play_axes_curve_scene,
    play_number_sequence,
    play_comparison_boxes,
    play_summary_scene,
)


CURVE_COLOR = GREEN
BAR_COLOR = BLUE_D
POINT_COLOR = ORANGE


class ExponentialGrowthStory(Scene):
    def construct(self):
        self.camera.background_color = BG_COLOR

        self.show_title()
        self.linear_vs_exponential()
        self.show_exponential_curve()
        self.real_world_examples()
        self.slow_then_explosive()
        self.chessboard_story()
        self.ending()

    # -------------------------
    # 1. 标题
    # -------------------------
    def show_title(self):
        play_title_card(
            self,
            title="Exponential Growth: Why the World Suddenly Explodes",
            subtitle="A Math Story About Doubling, Life, and Time",
            title_size=38,
            subtitle_size=24,
            title_color=TITLE_COLOR,
            subtitle_color=SUB_COLOR,
            hold_time=1.5,
        )

    # -------------------------
    # 2. 线性增长 vs 指数增长
    # -------------------------
    def linear_vs_exponential(self):
        header = en_text("1. Two Kinds of Growth", 30, TITLE_COLOR).to_edge(UP)
        note = en_text("One adds 1 each day; the other doubles each day.", 22, TEXT_COLOR).next_to(header, DOWN, buff=0.25)
        self.mobjects=[]
        self.mobjects.append(header)
        self.play(FadeIn(header), FadeIn(note), run_time=0.8)

        # 左：线性
        linear_title = en_text("Linear Growth", 26, BLUE).shift(LEFT * 3.5 + UP * 2)
        linear_nums = VGroup(*[
            en_text(str(i), 24, TEXT_COLOR) for i in [1, 2, 3, 4, 5, 6]
        ])
        linear_nums.arrange(RIGHT, buff=0.35).next_to(linear_title, DOWN, buff=0.5)

        linear_bars = VGroup()
        for i in range(1, 7):
            rect = Rectangle(
                width=0.35,
                height=0.25 * i,
                stroke_color=WHITE,
                stroke_width=1.5,
                fill_color=BAR_COLOR,
                fill_opacity=0.8
            )
            linear_bars.add(rect)
        linear_bars.arrange(RIGHT, aligned_edge=DOWN, buff=0.18)
        linear_bars.move_to(LEFT * 3.5 + DOWN * 1.2)

        # 右：指数
        expo_title = en_text("Exponential Growth", 26, GREEN).shift(RIGHT * 3.5 + UP * 2)
        expo_values = [1, 2, 4, 8, 16, 32]
        expo_nums = VGroup(*[
            en_text(str(v), 24, TEXT_COLOR) for v in expo_values
        ])
        expo_nums.arrange(RIGHT, buff=0.28).next_to(expo_title, DOWN, buff=0.5)

        expo_bars = VGroup()
        max_height = 3.2
        max_val = max(expo_values)
        for v in expo_values:
            h = max_height * (v / max_val)
            rect = Rectangle(
                width=0.35,
                height=max(0.18, h),
                stroke_color=WHITE,
                stroke_width=1.5,
                fill_color=GREEN_D,
                fill_opacity=0.8
            )
            expo_bars.add(rect)
        expo_bars.arrange(RIGHT, aligned_edge=DOWN, buff=0.18)
        expo_bars.move_to(RIGHT * 3.5 + DOWN * 1.2)

        self.play(FadeIn(linear_title), FadeIn(expo_title), run_time=0.6)

        for i in range(6):
            self.play(
                FadeIn(linear_nums[i], shift=UP * 0.1),
                GrowFromEdge(linear_bars[i], DOWN),
                FadeIn(expo_nums[i], shift=UP * 0.1),
                GrowFromEdge(expo_bars[i], DOWN),
                run_time=0.45
            )

        compare_note = en_text(
            "At first the difference is small, but later it becomes dramatic.",
            24,
            HIGHLIGHT_COLOR
        ).to_edge(DOWN)

        self.play(FadeIn(compare_note), run_time=0.7)
        self.wait(1.6)

        self.play(
            FadeOut(compare_note),
            FadeOut(linear_title), FadeOut(expo_title),
            FadeOut(linear_nums), FadeOut(expo_nums),
            FadeOut(linear_bars), FadeOut(expo_bars),
            FadeOut(note),
            run_time=0.8
        )
        self.play(header.animate.to_edge(UP), run_time=0.4)

    # -------------------------
    # 3. 指数函数曲线
    # -------------------------
    def show_exponential_curve(self):
        header, rendered = play_axes_curve_scene(
            self,
            header_text="2. Drawing Doubling as a Curve",
            x_range=[0, 6, 1],
            y_range=[0, 40, 10],
            plot_func=lambda x: 2**x,
            plot_x_range=[0, 5.2],
            note="If you multiply by the same factor every equal interval of time, the curve bends upward.",
            x_label_text="Time",
            y_label_text="Quantity",
            label_color=BAR_COLOR,
            formula_tex="y = 2^x",
            remark="This is the classic shape of exponential growth.",
            curve_color=CURVE_COLOR,
            point_x_values=[0, 1, 2, 3, 4, 5],
            point_y_func=lambda x: 2**x,
            point_color=POINT_COLOR,
            axes_shift=DOWN * 0.4,
        )
        self.play(FadeOut(rendered), run_time=0.9)

    # -------------------------
    # 4. 现实例子
    # -------------------------
    def real_world_examples(self):
        header = en_text("3. It Is More Than a Formula", 30, TITLE_COLOR).to_edge(UP)
        self.play(Transform(self.mobjects[0], header), run_time=0.6)

        items = [
            {
                "color": BLUE,
                "title": "Bacterial Growth",
                "body": "1 → 2 → 4 → 8",
                "width": 20,
            },
            {
                "color": GREEN,
                "title": "Viral Spread",
                "body": "One infected person can lead to many more infections",
                "width": 20,
            },
            {
                "color": ORANGE,
                "title": "Computing Power",
                "body": "Chips, parameters, and data are sometimes growing at an accelerating rate",
                "width": 20,
            },
        ]

        _, rendered = play_comparison_boxes(
            self,
            header_text="3. It Is More Than a Formula",
            header=header,
            note="Many systems seem to be quietly doubling in their early stages.",
            items=items,
            remark="What makes exponential growth frightening is that it often looks harmless at first.",
            box_width=3.8,
            box_height=2.6,
        )
        self.play(FadeOut(rendered), run_time=0.8)

    # -------------------------
    # 5. 慢，然后突然爆发
    # -------------------------
    def slow_then_explosive(self):
        play_number_sequence(
            self,
            header_text="4. The Danger Is That It Seems Slow at First",
            values=[1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024],
            color=TEXT_COLOR,
            show_arrows=False,
            remark="The explosion does not happen at the beginning. It appears only after enough accumulation.",
        )

    # -------------------------
    # 6. 棋盘与米粒
    # -------------------------
    def chessboard_story(self):
        header = en_text("5. Rice on a Chessboard", 30, TITLE_COLOR).to_edge(UP)
        self.play(Transform(self.mobjects[0], header), run_time=0.6)

        note = en_subtitle(
            "Legend says a man once asked a king for a reward:Place one grain of rice on the first square,two on the second,four on the third...doubling on every square。",
            22, TEXT_COLOR, line_spacing=0.8
        ).next_to(header, DOWN, buff=0.25)

        self.play(FadeIn(note), run_time=0.9)

        board = VGroup()
        size = 0.45
        for r in range(4):
            row = VGroup()
            for c in range(4):
                sq = Square(side_length=size)
                sq.set_stroke(GRAY_B, 1.2)
                sq.set_fill(opacity=0)
                row.add(sq)
            row.arrange(RIGHT, buff=0)
            board.add(row)
        board.arrange(DOWN, buff=0)
        board.shift(LEFT * 2 + DOWN * 0.8)

        self.play(Create(board), run_time=1.0)

        # 前16格示意
        values = [2**i for i in range(16)]
        value_labels = VGroup()
        for i, v in enumerate(values):
            rr = i // 4
            cc = i % 4
            label = MathTex(str(v), color=FORMULA_COLOR).scale(0.42)
            label.move_to(board[rr][cc].get_center())
            value_labels.add(label)

        self.play(LaggedStart(*[FadeIn(v, scale=0.8) for v in value_labels], lag_ratio=0.08), run_time=1.5)

        arrow = Arrow(start=board.get_corner(DR),end=RIGHT * 3.5 + UP * 0.4,color=YELLOW)
        big_formula = MathTex("2^{63}", color=YELLOW).scale(1.4).move_to(RIGHT * 4 + UP * 0.4)
        big_num = MathTex(r"\approx 9.22 \times 10^{18}", color=FORMULA_COLOR).scale(0.9).next_to(big_formula, DOWN, buff=0.25)
        final_text = en_text("By the 64th square, \nthe number is already beyond imagination.", 24, HIGHLIGHT_COLOR).move_to(RIGHT * 4 + DOWN * 1.0)

        self.play(GrowArrow(arrow), run_time=0.8)
        self.play(Write(big_formula), FadeIn(big_num), FadeIn(final_text), run_time=1.2)
        self.wait(2.0)

        self.play(
            FadeOut(note), FadeOut(board), FadeOut(value_labels),
            FadeOut(arrow), FadeOut(big_formula), FadeOut(big_num), FadeOut(final_text),
            run_time=0.9
        )

    # -------------------------
    # 7. 结尾
    # -------------------------
    def ending(self):
        play_summary_scene(
            self,
            summary_lines=[
                "The frightening thing about exponential growth is not how fast it starts,",
                "but how it quietly accumulates before you even notice it.",
                "Then, at some moment, it suddenly explodes.",
            ],
            line_size=28,
            line_color=TEXT_COLOR,
            highlight_last=True,
            highlight_color=HIGHLIGHT_COLOR,
            formula_tex=r"1, 2, 4, 8, 16, 32, \\dots",
            formula_color=CURVE_COLOR,
            formula_scale=1.1,
            footer_text="Next time: if splitting and reproduction continue nonstop, what does continuous exponential growth lead to?",
            footer_size=20,
            footer_color=HIGHLIGHT_COLOR,
            footer_as_subtitle=True,
            wait_time=2.5,
        )
        fade_out_all(self, run_time=1.0)
