# Mailpile configuration draft spec (2013-10-11)

The goals for the new configuration system are:

   1. Allow plugins to register new sections in a developer-friendly
      manner
   2. Make the configuration self documenting as much as possible
   3. Make the configuration verifiable, so all values are checked for
      validity
   
Code which accomplishes these 3 goals has been written (see
`mailpile/config.py`). This document is describes the format used to define
configuration itself; they are are written as JSON (or the equivalent Python
dicts).  A variable is defined using a list of three values: [comment,
type/constraint, default-value].

A fictional example of simple settings:

    "search": ["Search related settings", false,
    {
        "max_results": ["The max number of search results per page",
                        "int",
                        20],
        "default_order": ["The default sort order.",
                          ["date", "reverse-date", ... ],
                          "reverse-date"]
    }]

Here a section of the configuration is defined named "search", which
contains the settings "max_results" and "default_order". The
"max_results" is defined as an integer with the default value of 20, and
the "default_order" is a string which must match one of the listed
values.

Settings can be nested using the same syntax, where instead of a default
value, a dictionary of sub-variables and their defintions is present
instead:

    "preferences": ["User preferences", false,
    {
        "user-interface": ["User interface", false, {
            "color-scheme": ["Preferred color scheme",
                             ["light", "dark", "colorblind"],
                             "light"],
            "hotkeys": ["Keybinding style",
                        ["emacs", "gmail", "vi", "mailpile"],
                        "mailpile"]
            ...
        }],
        ...
    }]

Finally, lists or dictionaries of structured elements can be defined by
setting the default value to an empty list [] or dictionary {}, and
provide a description of what each element should look like in the
type/constraint field:

    "tags": ["The tags used by the system",
             {
                 "name": ["The tag name", unicode, "Unnamed Tag"],
                 "slug": ["Slug for URLs etc.", unicode, "UnnamedTag"],
                  ...
             },
             []]

    "tagdict": ["The tags used by the system",
                {
                   "name": ["The tag name", unicode, "Unnamed Tag"],
                   "slug": ["Slug for URLs etc.", unicode, "UnnamedTag"],
                   ...
                },
                {}]

In the Python code, this structure would be manipulated like so:

    # Note: config['tags'] and config.tags are the same thing
    config.tags.append({
        "name": 'Watever',
        'slug': 'watever'
    })

    config.tagdict['mytag'] = {
        "name": 'Watever',
        'slug': 'watever'
    }

... would succeed.  However these would throw an exception:

    config.tags.append({
        "name": 'Watever',
        'slog': 'watever',
        'bogon': 'invalid crap'
    })

    config.tagdict.mytag'] = {
        "name": 'Watever',
        'slog': 'watever',
        'bogon': 'invalid crap'
    }


## Known limitations ##

   * Currently it is not possible to specify that some settings
     are mandatory and **must** be set (all are considered optional)
   * There is no concept of privacy in this yet
   * There is no constraint on what keys can be used in a structured
     dictionary


## Points for the future ##

   * We need to choose a configuration file format
   * We will want to be able to import/export/backup settings
   * We will want a "safe export@ that doesn't leak passwords etc

