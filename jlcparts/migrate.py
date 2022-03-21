import click
from .partLib import PartLibrary, PartLibraryDb


@click.command()
@click.argument("input")
@click.argument("output")
def migrate_to_db(input, output):
    pLib = PartLibrary(input)
    dbLib = PartLibraryDb(output)

    with dbLib.startTransaction():
        l = len(pLib.index)
        for i, id in enumerate(pLib.index.keys()):
            c = pLib.getComponent(id)
            if i % 1000 == 0:
                print(f"{((i+1) / l * 100):.2f} %")
            dbLib.addComponent(c)


if __name__ == "__main__":
    migrate_to_db()
