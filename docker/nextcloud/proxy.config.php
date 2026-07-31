<?php
$trustedProxies = array_filter(array_map('trim', explode(',', getenv('NEXTCLOUD_TRUSTED_PROXIES') ?: 'nginx')));
$trustedDomains = preg_split('/[\s,]+/', trim(getenv('NEXTCLOUD_TRUSTED_DOMAINS') ?: 'messagerie.dges.local'));
$trustedDomains = array_values(array_filter(array_map('trim', $trustedDomains)));
$overwriteHost = trim(getenv('NEXTCLOUD_OVERWRITEHOST') ?: '');
$overwriteCliUrl = trim(getenv('NEXTCLOUD_OVERWRITE_CLI_URL') ?: '');

$configOverrides = [
    'overwriteprotocol' => getenv('NEXTCLOUD_OVERWRITEPROTOCOL') ?: 'https',
    'trusted_domains' => array_values(array_unique(array_merge($CONFIG['trusted_domains'] ?? [], $trustedDomains))),
    'trusted_proxies' => $trustedProxies,
];

if ($overwriteHost !== '') {
    $configOverrides['overwritehost'] = $overwriteHost;
}

if ($overwriteCliUrl !== '') {
    $configOverrides['overwrite.cli.url'] = $overwriteCliUrl;
}

$CONFIG = array_merge($CONFIG ?? [], $configOverrides);
