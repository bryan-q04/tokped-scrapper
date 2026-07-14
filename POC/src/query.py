"""The GraphQL queries sent to Tokopedia's internal endpoints.

SEARCH_QUERY: SearchProductV5Query (verified against a live capture, 2026-07).
  - root field: searchProductV5 ; products at data.searchProductV5.data.products
  - id fields are aliased: oldID = numeric id, id = string id
  - price is an object {text, number}; sold count lives in labelGroups (position "integrity")
  - shop has `tier` (2 = Mall/Official Store, 3 = Power Shop) instead of isOfficial

PDP_QUERY: product-detail for exact sold — NOT yet verified against a live capture.
  Needs Phase 0 capture #2; fetch_count_sold() fails gracefully until then.
"""

SEARCH_QUERY = """
query SearchProductV5Query($params: String!) {
  searchProductV5(params: $params) {
    header {
      totalData
      responseCode
      keywordProcess
      componentID
    }
    data {
      totalDataText
      products {
        oldID: id
        id: id_str_auto_
        name
        url
        applink
        price {
          text
          number
          original
          discountPercentage
        }
        shop {
          oldID: id
          id: id_str_auto_
          name
          url
          city
          tier
        }
        badge {
          title
          url
        }
        labelGroups {
          position
          title
          type
          url
        }
        rating
        wishlist
        ads {
          id
          tag
        }
      }
    }
  }
}
""".strip()


# Product-detail query for the EXACT sold count (txStats.countSold).
# UNVERIFIED — replace with the real op once Phase 0 capture #2 is done. The extractor
# searches recursively for `countSold`, so it tolerates extra nesting.
PDP_QUERY = """
query PDPGetLayoutQuery($shopDomain: String, $productKey: String, $layoutID: String, $apiVersion: Float) {
  pdpGetLayout(shopDomain: $shopDomain, productKey: $productKey, layoutID: $layoutID, apiVersion: $apiVersion) {
    basicInfo {
      id
      txStats {
        countSold
        transactionSuccess
      }
    }
  }
}
""".strip()
