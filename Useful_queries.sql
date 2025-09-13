-- STATISTICS ABOUT FLIGHTS, TRACKS
-- Flights table statistics
SELECT
	MIN(f.first_seen  ) AS oldest_flight,
	MAX(f.first_seen  ) AS most_recent_flight,
	COUNT(DISTINCT f.fr24_id )
FROM flights f;

-- Tracks table statistics
SELECT
	MIN(t."timestamp" ) AS oldest_track,
	MAX(t."timestamp" ) AS most_recent_track,
	COUNT(DISTINCT t.fr24_id )
FROM tracks t;

-- List all ZRH airport runways
SELECT 
	DISTINCT f.runway_takeoff 
FROM flights f
WHERE f.orig_iata = "ZRH"
UNION ALL
SELECT 
	DISTINCT f2.runway_landed, f2.dest_iata 
FROM flights f2
WHERE f2.dest_iata = "ZRH";

-- Diverted flights : ZRH only has Runway 10,14,16,28,32,34
SELECT 
	f.runway_landed,
	COUNT(*)
FROM flights f
WHERE 
	f.dest_iata  = "ZRH"
	AND f.runway_landed NOT IN (10,14,16,28,32,34)
GROUP BY f.runway_landed 

-- All Flights with no tracks
SELECT
	"From" AS from_to,
	f.orig_iata AS airport,
	f.runway_takeoff AS runway, 
	COUNT(*)
FROM flights f
LEFT JOIN tracks t
ON f.fr24_id = t.fr24_id 
WHERE 
	TRUE
	AND t.fr24_id IS NULL
	AND f.fr24_id NOT IN (SELECT DISTINCT fr24_id FROM tracks)
	AND f.requires_update IS FALSE
	AND f.orig_iata = "ZRH"
GROUP BY f.orig_iata, f.runway_takeoff
UNION ALL
SELECT
	"To" AS from_to,
	f.dest_iata  AS airport,
	f.runway_takeoff AS runway, 
	COUNT(*)
FROM flights f
LEFT JOIN tracks t
ON f.fr24_id = t.fr24_id 
WHERE 
	TRUE
	AND t.fr24_id IS NULL
	AND f.fr24_id NOT IN (SELECT DISTINCT fr24_id FROM tracks)
	AND f.requires_update IS FALSE
	AND f.dest_iata  = "ZRH"
GROUP BY f.dest_iata, f.runway_takeoff;

-- All flights with no tracks, filtered on ZRH airport runways
SELECT *
FROM (
SELECT
	"From" AS from_to,
	f.orig_iata AS airport,
	f.runway_takeoff AS runway, 
	COUNT(*)
FROM flights f
LEFT JOIN tracks t
ON f.fr24_id = t.fr24_id 
WHERE 
	TRUE
	AND t.fr24_id IS NULL
	AND f.fr24_id NOT IN (SELECT DISTINCT fr24_id FROM tracks)
	AND f.requires_update IS FALSE
	AND f.orig_iata = "ZRH"
GROUP BY f.orig_iata, f.runway_takeoff
UNION ALL
SELECT
	"To" AS from_to,
	f.dest_iata  AS airport,
	f.runway_takeoff AS runway, 
	COUNT(*)
FROM flights f
LEFT JOIN tracks t
ON f.fr24_id = t.fr24_id 
WHERE 
	TRUE
	AND t.fr24_id IS NULL
	AND f.fr24_id NOT IN (SELECT DISTINCT fr24_id FROM tracks)
	AND f.requires_update IS FALSE
	AND f.dest_iata  = "ZRH"
GROUP BY f.dest_iata, f.runway_takeoff)
WHERE runway IN (10,14,16,28,32,34)

-- FLIGHTS
-- Most popular types of planes
SELECT 
	f."type",
	i.manufacturer_code,
	i.model_no,
	i.wtc,
	COUNT(*) AS COUNT,
	ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM flights), 2) AS pct
FROM flights f
LEFT JOIN icao_8643 i 
ON f."type" = i.tdesig 
GROUP by f."type" 
ORDER BY COUNT(*) DESC

  SELECT
      DATE(datetime_takeoff) as flight_date,
      COUNT(*) as flights_per_day
  FROM flights
  WHERE datetime_takeoff IS NOT NULL
  GROUP BY DATE(datetime_takeoff)
  ORDER BY flight_date;

              