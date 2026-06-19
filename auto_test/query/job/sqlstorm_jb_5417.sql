SELECT
    a.name AS actor_name,
    t.title AS movie_title,
    t.production_year,
    r.role AS role,
    cp.name AS company_name,
    kt.keyword AS keyword
FROM
    cast_info AS c
JOIN
    aka_name AS a ON c.person_id = a.person_id
JOIN
    title AS t ON c.movie_id = t.id
JOIN
    role_type AS r ON c.role_id = r.id
JOIN
    movie_companies AS mc ON t.id = mc.movie_id
JOIN
    company_name AS cp ON mc.company_id = cp.id
LEFT JOIN
    movie_keyword AS mk ON t.id = mk.movie_id
LEFT JOIN
    keyword AS kt ON mk.keyword_id = kt.id
WHERE
    t.production_year BETWEEN 2000 AND 2023
    AND r.role IN (SELECT role FROM role_type WHERE role LIKE '%Actor%');
