# OpenSearch 2.x + Korean (Nori) analyzer plugin.
# k-NN plugin is bundled in the official image.
ARG OPENSEARCH_VERSION=2.15.0
FROM opensearchproject/opensearch:${OPENSEARCH_VERSION}
RUN /usr/share/opensearch/bin/opensearch-plugin install --batch analysis-nori
