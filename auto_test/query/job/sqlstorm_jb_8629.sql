SELECT
    a.name AS actor_name,
    t.title AS movie_title,
    c.kind AS cast_type,
    ci.note AS role_note,
    COUNT(k.id) AS keyword_count
FROM
    aka_name AS a
JOIN
    cast_info AS ci ON a.person_id = ci.person_id
JOIN
    title AS t ON ci.movie_id = t.id
JOIN
    comp_cast_type AS c ON ci.person_role_id = c.id
LEFT JOIN
    movie_keyword AS mk ON mk.movie_id = t.id
LEFT JOIN
    keyword AS k ON mk.keyword_id = k.id
WHERE
    t.production_year >= 2000
    AND a.name IS NOT NULL
GROUP BY
    a.name, t.title, c.kind, ci.note;
