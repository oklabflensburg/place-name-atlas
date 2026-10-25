from atlas.schemas import Group, Pattern, PresetOut


def preset(id, title, parts, mode="suffix"):
    colors = ["#126b61", "#b95030", "#6953a5", "#a16c12"]
    return PresetOut(id=id, title=title,
        description="Vergleich von Schreibformen. Zeichenübereinstimmungen belegen keine gemeinsame Namensherkunft.",
        groups=[Group(id=f"g{i+1}", title=" / ".join(p), color=colors[i],
                      patterns=[Pattern(mode=mode, value=v) for v in p]) for i, p in enumerate(parts)])


PRESETS = [
    preset("ing-ingen", "-ing und -ingen", [["ing"], ["ingen"]]),
    preset("bach-bek", "-bach, -bek, -beck, -beek", [["bach"], ["bek"], ["beck"], ["beek"]]),
    preset("hausen-husen", "-hausen, -husen, -huusen", [["hausen"], ["husen"], ["huusen"]]),
    preset("by-buell", "-by, -büll, -büttel", [["by"], ["büll"], ["büttel"]]),
    preset("dorf-berg", "-dorf, -berg, -burg, -heim", [["dorf"], ["berg"], ["burg"], ["heim"]]),
    preset("otter", "Enthält otter", [["otter"]], "contains"),
]
