import unittest

from meteoblue_seeing.ukv_aws import _nearest_index, parse_s3_keys, parse_s3_prefixes


class TestAwsListingParsing(unittest.TestCase):
    def test_parses_run_prefixes(self):
        xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
          <CommonPrefixes><Prefix>uk-deterministic-2km/20260927T1500Z/</Prefix></CommonPrefixes>
          <CommonPrefixes><Prefix>uk-deterministic-2km/20260927T1700Z/</Prefix></CommonPrefixes>
        </ListBucketResult>"""
        self.assertEqual(
            parse_s3_prefixes(xml),
            [
                "uk-deterministic-2km/20260927T1500Z/",
                "uk-deterministic-2km/20260927T1700Z/",
            ],
        )

    def test_parses_object_keys(self):
        xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
          <IsTruncated>false</IsTruncated>
          <Contents><Key>one.nc</Key></Contents>
          <Contents><Key>two.nc</Key></Contents>
        </ListBucketResult>"""
        self.assertEqual(parse_s3_keys(xml), ["one.nc", "two.nc"])

    def test_nearest_index(self):
        values = [-100.0, 0.0, 100.0, 200.0]
        self.assertEqual(_nearest_index(values, 40.0), 1)
        self.assertEqual(_nearest_index(values, 60.0), 2)
        self.assertEqual(_nearest_index(values, -500.0), 0)
        self.assertEqual(_nearest_index(values, 500.0), 3)


if __name__ == "__main__":
    unittest.main()
