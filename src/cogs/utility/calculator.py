"""
KYOKA 3.0 — Mathematical Calculator Utility.
Safe AST-based arithmetic expression evaluator.
"""

from __future__ import annotations

import ast
import math
import operator
from typing import TYPE_CHECKING
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext

if TYPE_CHECKING:
    from src.core.bot import KyokaBot


SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def safe_eval(node: ast.AST) -> float | int:
    """Safely evaluate AST math nodes without arbitrary code execution."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("Non-numeric constant detected.")

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in SAFE_OPERATORS:
            raise ValueError(f"Unsupported operator: {op_type.__name__}")
        left = safe_eval(node.left)
        right = safe_eval(node.right)
        if op_type == ast.Pow and (abs(right) > 100 or abs(left) > 1000):
            raise ValueError("Exponent too large to compute safely.")
        if op_type in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
            raise ZeroDivisionError("Division by zero.")
        return SAFE_OPERATORS[op_type](left, right)

    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in SAFE_OPERATORS:
            raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
        return SAFE_OPERATORS[op_type](safe_eval(node.operand))

    raise ValueError("Invalid mathematical expression.")


class Calculator(commands.Cog):
    """Safe mathematical computation utility."""

    category = "🔧・UTILITIES"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    @commands.command(
        name="calc",
        aliases=["calculator", "math"],
        description="Calculate a mathematical expression safely (e.g. 25 * 4 + 10).",
    )
    async def calc(self, ctx: CustomContext, *, expression: str) -> None:
        """Evaluate a mathematical expression."""
        clean_expr = expression.replace("^", "**").replace("x", "*").replace("X", "*")
        try:
            parsed = ast.parse(clean_expr, mode="eval")
            result = safe_eval(parsed.body)
            # Format nicely
            if isinstance(result, float) and result.is_integer():
                result = int(result)
            elif isinstance(result, float):
                result = round(result, 6)

            embed = discord.Embed(
                title="🧮 Calculator",
                color=0x7C3AED,
            )
            embed.add_field(name="Expression", value=f"`{expression}`", inline=False)
            embed.add_field(name="Result", value=f"```\n{result}\n```", inline=False)
            await ctx.send(embed=embed)
        except ZeroDivisionError:
            await ctx.send("❌ Cannot divide by zero.")
        except Exception as e:
            await ctx.send(f"❌ Invalid expression: `{e}`")


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(Calculator(bot))
