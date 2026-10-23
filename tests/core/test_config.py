import pytest

from organize.config import Config, ConfigError
from organize.errors import IncludeError


def test_basic():
    x = Config.from_string(
        """
    rules:
    - locations: '~/'
      filters:
      - extension:
        - jpg
        - png
      - extension: txt
      actions:
      - move:
          dest: '~/New Folder'
      - echo: 'Moved {path}/{extension.upper()}'
    - locations:
      - path: '~/test1'
        ignore_errors: true
      actions:
      - shell:
          cmd: 'say {path.stem}'
    """
    )
    print(x)


def test_yaml_ref():
    x = Config.from_string(
        """
    media: &media
      - wav
      - png

    all_folders: &all
      / "~"
      - "/"

    rules:
      - locations: *all
        filters:
          - extension: *media
          - extension:
            - *media
            - jpg
          - lastmodified:
              days: 10
        actions:
          - echo: 'Hello World'
      - locations:
          - *all
          - path: /more/more
            ignore_errors: true
        actions:
          - trash
    """
    )
    print(x)


def test_error_filter_dict():
    STR = """
    rules:
    - locations: '/'
      filters:
        extension: 'jpg'
        name: test
      actions:
      - trash
    """
    with pytest.raises(ConfigError):
        print(Config.from_string(STR))


def test_error_action_dict():
    config = """
        rules:
          - locations: '/'
            filters:
              - extension: 'jpg'
            actions:
              Trash
              Echo
    """
    with pytest.raises(ConfigError):
        Config.from_string(config)


def test_empty_filters():
    conf = """
    rules:
      - locations: '/'
        filters:
        actions:
          - trash
      - locations: '~/'
        actions:
          - trash
    """
    assert Config.from_string(conf)


def test_issue352():
    conf = """
    all_my_messy__download_folders: &download_folders
      - D:/Windows/Downloads/Chrome
      - D:/Windows/Downloads/Chrome/Other

    rules:
      - name: "Delete Duplicate"
        locations: *download_folders
        filters:
          - duplicate:
              detect_original_by: "created"
        actions:
          - delete
    """
    assert Config.from_string(conf)


def test_flatten_filters_and_actions():
    config = """
    folder_aliases:
      Downloads: &downloads ~/Downloads/
      Payables_due: &payables_due ~/PayablesDue/
      Payables_paid: &payables_paid ~/Accounting/Expenses/
      Receivables_due: &receivables_due ~/Receivables/
      Receivables_paid: &receivables_paid ~/Accounting/Income/

    defaults:
      filters: &default_filters
        - extension: pdf
        - filecontent: '(?P<date>...)'
      actions: &default_actions
        - echo: 'Dated: {filecontent.date}'
        - echo: 'Stem of filename: {filecontent.stem}'
      post_actions: &default_sorting
        - rename: '{python.timestamp}-{filecontent.stem}.{extension.lower}'
        - move: '{path.parent}/{python.quarter}/'

    rules:
      - locations: *downloads
        filters:
          - *default_filters
          - filecontent: 'Due Date' # regex to id as payable
          - filecontent: '(?P<stem>...)' # regex to extract supplier
        actions:
          - *default_actions
          - move: *payables_due
          - *default_sorting

      - locations: *downloads
        filters:
          - *default_filters
          - filecontent: 'Account: 000000000' # regex to id as receivables due
          - filecontent: '(?P<stem>...)' # regex to extract customer
        actions:
          - *default_actions
          - move: *receivables_due
          - *default_sorting

      - locations: *downloads
        filters:
          - *default_filters
          - filecontent: 'PAID' # regex to id as receivables paid
          - filecontent: '(?P<stem>...)' # regex to extract customer
          - filecontent: '(?P<paid>...)' # regex to extract date paid
          - name:
              startswith: 2020
        actions:
          - *default_actions
          - move: *receivables_paid
          - *default_sorting
          - rename: '{filecontent.paid}_{filecontent.stem}.{extension}'
    """
    Config.from_string(config)


#     assert conf.rules == [
#         Rule(
#             folders=["~/Downloads/"],
#             filters=[
#                 # default_filters
#                 Extension("pdf"),
#                 FileContent(expr="(?P<date>...)"),
#                 # added filters
#                 FileContent(expr="Due Date"),
#                 FileContent(expr="(?P<stem>...)"),
#             ],
#             actions=[
#                 # default_actions
#                 Echo(msg="Dated: {filecontent.date}"),
#                 Echo(msg="Stem of filename: {filecontent.stem}"),
#                 # added actions
#                 Move(dest="~/PayablesDue/", overwrite=False),
#                 # default_sorting
#                 Rename(
#                     name="{python.timestamp}-{filecontent.stem}.{extension.lower}",
#                     overwrite=False,
#                 ),
#                 Move(dest="{path.parent}/{python.quarter}/", overwrite=False),
#             ],
#             subfolders=False,
#             system_files=False,
#         ),
#         Rule(
#             folders=["~/Downloads/"],
#             filters=[
#                 # default_filters
#                 Extension("pdf"),
#                 FileContent(expr="(?P<date>...)"),
#                 # added filters
#                 FileContent(expr="Account: 000000000"),
#                 FileContent(expr="(?P<stem>...)"),
#             ],
#             actions=[
#                 # default_actions
#                 Echo(msg="Dated: {filecontent.date}"),
#                 Echo(msg="Stem of filename: {filecontent.stem}"),
#                 # added actions
#                 Move(dest="~/Receivables/", overwrite=False),
#                 # default_sorting
#                 Rename(
#                     name="{python.timestamp}-{filecontent.stem}.{extension.lower}",
#                     overwrite=False,
#                 ),
#                 Move(dest="{path.parent}/{python.quarter}/", overwrite=False),
#             ],
#             subfolders=False,
#             system_files=False,
#         ),
#         Rule(
#             folders=["~/Downloads/"],
#             filters=[
#                 # default_filters
#                 Extension("pdf"),
#                 FileContent(expr="(?P<date>...)"),
#                 # added filters
#                 FileContent(expr="PAID"),
#                 FileContent(expr="(?P<stem>...)"),
#                 FileContent(expr="(?P<paid>...)"),
#                 Filename(startswith="2020"),
#             ],
#             actions=[
#                 # default_actions
#                 Echo(msg="Dated: {filecontent.date}"),
#                 Echo(msg="Stem of filename: {filecontent.stem}"),
#                 # added actions
#                 Move(dest="~/Accounting/Income/", overwrite=False),
#                 # default_sorting
#                 Rename(
#                     name="{python.timestamp}-{filecontent.stem}.{extension.lower}",
#                     overwrite=False,
#                 ),
#                 Move(dest="{path.parent}/{python.quarter}/", overwrite=False),
#                 # added actions
#                 Rename(
#                     name="{filecontent.paid}_{filecontent.stem}.{extension}",
#                     overwrite=False,
#                 ),
#             ],
#             subfolders=False,
#             system_files=False,
#         ),
#     ]


BASE_CONFIG = """\
ext_images: &ext_images
  - jpg
  - png

folder_images: &Images_Folders
  - '~/Downloads'
  - '~/Pictures/'
"""

CHILD_CONFIG = """\
include: base.yaml

rules:
  - name: 'Images rule'
    locations: *Images_Folders
    filters:
      - extension: *ext_images
    actions:
      - echo: 'img {path.name}'
"""


def test_include_anchors(tmp_path):
    (tmp_path / "base.yaml").write_text(BASE_CONFIG)
    (tmp_path / "child.yaml").write_text(CHILD_CONFIG)

    conf = Config.from_path(tmp_path / "child.yaml")

    assert [rule.name for rule in conf.rules] == ["Images rule"]
    rule = conf.rules[0]
    locations = [path for loc in rule.locations for path in loc.path]
    assert locations == ["~/Downloads", "~/Pictures/"]
    assert rule.filters[0].extensions == {"jpg", "png"}


def test_include_list(tmp_path):
    (tmp_path / "base.yaml").write_text(BASE_CONFIG)
    (tmp_path / "extra.yaml").write_text(
        """\
ext_docs: &ext_docs
  - pdf
  - epub
"""
    )
    (tmp_path / "child.yaml").write_text(
        """\
include:
  - base.yaml
  - extra.yaml

rules:
  - name: 'Child rule'
    locations: '~/Downloads'
    filters:
      - extension: *ext_docs
    actions:
      - echo: 'child'
"""
    )

    conf = Config.from_path(tmp_path / "child.yaml")

    assert len(conf.rules) == 1
    assert conf.rules[0].filters[0].extensions == {"pdf", "epub"}


def test_include_nested(tmp_path):
    (tmp_path / "base.yaml").write_text(BASE_CONFIG)
    (tmp_path / "middle.yaml").write_text(
        """\
include: base.yaml

ext_docs: &ext_docs
  - pdf
"""
    )
    (tmp_path / "child.yaml").write_text(
        """\
include: middle.yaml

rules:
  - name: 'Child rule'
    locations: *Images_Folders
    filters:
      - extension: *ext_docs
      - extension: *ext_images
    actions:
      - echo: 'child'
"""
    )

    conf = Config.from_path(tmp_path / "child.yaml")

    rule = conf.rules[0]
    assert rule.filters[0].extensions == {"pdf"}
    assert rule.filters[1].extensions == {"jpg", "png"}
    locations = [path for loc in rule.locations for path in loc.path]
    assert locations == ["~/Downloads", "~/Pictures/"]


def test_include_cycle(tmp_path):
    (tmp_path / "a.yaml").write_text(
        """\
include: b.yaml

rules:
  - name: 'A'
    locations: '~/'
    actions:
      - echo: a
"""
    )
    (tmp_path / "b.yaml").write_text(
        """\
include: a.yaml

rules:
  - name: 'B'
    locations: '~/'
    actions:
      - echo: b
"""
    )

    with pytest.raises(IncludeError):
        Config.from_path(tmp_path / "a.yaml")


def test_include_missing(tmp_path):
    (tmp_path / "child.yaml").write_text(
        """\
include: does_not_exist.yaml

rules:
  - name: 'Child'
    locations: '~/'
    actions:
      - echo: child
"""
    )

    with pytest.raises(IncludeError):
        Config.from_path(tmp_path / "child.yaml")
