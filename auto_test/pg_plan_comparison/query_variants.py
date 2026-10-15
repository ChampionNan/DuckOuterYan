"""Small, lossless transformations for the benchmark SQL used in this study."""


def top_level_tokens(sql):
    """Locate unquoted SQL words outside parentheses, strings and comments."""
    tokens = []
    index = depth = 0
    while index < len(sql):
        char = sql[index]
        if sql.startswith('--', index):
            end = sql.find('\n', index + 2)
            index = len(sql) if end < 0 else end + 1
        elif sql.startswith('/*', index):
            nesting = 1
            index += 2
            while index < len(sql) and nesting:
                if sql.startswith('/*', index):
                    nesting += 1
                    index += 2
                elif sql.startswith('*/', index):
                    nesting -= 1
                    index += 2
                else:
                    index += 1
            if nesting:
                raise ValueError('unterminated SQL comment')
        elif char in "'\"":
            quote = char
            index += 1
            while index < len(sql):
                if sql[index] == quote:
                    index += 1
                    if index < len(sql) and sql[index] == quote:
                        index += 1
                    else:
                        break
                else:
                    index += 1
            else:
                raise ValueError('unterminated SQL quote')
        elif char == '$':
            raise ValueError('dollar-quoted SQL is outside this benchmark transformer')
        elif char == '(':
            depth += 1
            index += 1
        elif char == ')':
            depth -= 1
            if depth < 0:
                raise ValueError('unbalanced SQL parentheses')
            index += 1
        elif char.isalpha() or char == '_':
            start = index
            index += 1
            while index < len(sql) and (sql[index].isalnum() or sql[index] == '_'):
                index += 1
            if depth == 0:
                tokens.append((sql[start:index].upper(), start, index))
        else:
            index += 1
    if depth:
        raise ValueError('unbalanced SQL parentheses')
    return tokens


def strip_outer_order_limit(sql):
    tokens = top_level_tokens(sql)
    candidates = []
    for index, (word, start, _) in enumerate(tokens):
        if word == 'LIMIT' or (word == 'ORDER' and index + 1 < len(tokens) and tokens[index + 1][0] == 'BY'):
            candidates.append(start)
    if not candidates:
        return sql, {'changed': False, 'removed_suffix': ''}
    cut = min(candidates)
    if any(word in {'SELECT', 'UNION', 'EXCEPT', 'INTERSECT', 'WHERE', 'HAVING', 'GROUP'}
           for word, start, _ in tokens if start > cut):
        raise ValueError('presentation clause is not a terminal outer-query suffix')
    # Preserve the prefix byte-for-byte, including a newline terminating any
    # immediately preceding line comment.
    return sql[:cut] + ';\n', {'changed': True, 'removed_suffix': sql[cut:], 'cut_offset': cut}
