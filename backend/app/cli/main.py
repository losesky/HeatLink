import click

from app.cli.news import news


@click.group()
def cli():
    """HeatLink CLI 工具"""
    pass


# 添加子命令
cli.add_command(news)


if __name__ == "__main__":
    cli() 