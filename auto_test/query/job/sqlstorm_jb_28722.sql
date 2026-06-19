
WITH movie_ratings AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        AVG(CASE 
            WHEN r.rating IS NOT NULL THEN r.rating 
            ELSE 0 
        END) AS average_rating
    FROM 
        title t
    LEFT JOIN 
        movie_info mi ON t.id = mi.movie_id AND mi.info_type_id = (SELECT id FROM info_type WHERE info = 'rating')
    LEFT JOIN 
        (SELECT 
            movie_id, 
            CAST(info AS FLOAT) AS rating 
        FROM 
            movie_info 
        WHERE 
            info_type_id = (SELECT id FROM info_type WHERE info = 'rating')) r 
    ON 
        t.id = r.movie_id
    GROUP BY 
        t.id, t.title
),
person_with_movies AS (
    SELECT 
        a.name AS actor_name,
        t.title AS movie_title,
        c.nr_order AS role_order,
        p.gender,
        mr.average_rating
    FROM 
        aka_name a
    JOIN 
        cast_info c ON a.person_id = c.person_id
    JOIN 
        title t ON c.movie_id = t.id
    LEFT JOIN 
        movie_ratings mr ON t.id = mr.movie_id
    JOIN 
        name p ON a.person_id = p.imdb_id
    WHERE 
        p.gender = 'F'
),
final_results AS (
    SELECT 
        actor_name,
        movie_title,
        role_order,
        average_rating,
        ROW_NUMBER() OVER (PARTITION BY actor_name ORDER BY average_rating DESC) AS rank
    FROM 
        person_with_movies
)
SELECT 
    actor_name,
    movie_title,
    role_order,
    average_rating
FROM 
    final_results
WHERE 
    rank <= 5;
