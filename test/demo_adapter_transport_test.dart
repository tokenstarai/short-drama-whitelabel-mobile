import 'package:flutter_test/flutter_test.dart';
import 'package:short_drama_whitelabel/app/demo_adapter_transport.dart';
import 'package:short_drama_whitelabel/core/api/tenant_adapter_client.dart';
import 'package:short_drama_whitelabel/flavor/flavor.dart';

void main() {
  test('demo transport serves a complete local app flow', () async {
    final client = TenantAdapterClient(
      baseUri: Uri.parse('https://tenant-edge.example.test'),
      transport: DemoAdapterTransport(
        flavor: FlavorConfig.coolshow(),
        endUserRef: 'anon:coolshow-demo-device',
      ),
    );

    final config = await client.fetchConfig();
    final catalog = await client.fetchCatalog();
    final detail = await client.fetchDrama(catalog.first.dramaId);
    final paidEpisode = detail.episodes.firstWhere(
      (episode) => episode.ready && episode.locked,
    );
    final walletBefore = await client.fetchWallet();
    final play = await client.authorizePlayback(
      dramaId: detail.drama.dramaId,
      episodeId: paidEpisode.episodeId,
      endUserRef: 'anon:coolshow-demo-device',
      idempotencyKey: 'demo-play-test',
    );
    final card = await client.redeemConsumerCard(
      cardCode: 'DEMO-VIP-001',
      endUserRef: 'anon:coolshow-demo-device',
      idempotencyKey: 'demo-card-test',
    );
    final intent = await client.createPaymentIntent(
      provider: 'stripe',
      packageId: 'coins_100',
      amountOriginal: 9,
      currency: 'USD',
      endUserRef: 'anon:coolshow-demo-device',
      idempotencyKey: 'demo-pay-test',
    );
    final walletAfter = await client.fetchWallet();
    final ledger = await client.fetchWalletLedger();
    final deleteRequest = await client.submitAccountDelete(
      accountRef: 'anon:coolshow-demo-device',
    );

    expect(config.appName, 'CoolShow Short');
    expect(config.capabilities.styleTemplate.wireValue, 'coolshow');
    expect(catalog, isNotEmpty);
    expect(detail.episodes.length, detail.drama.episodeCount);
    expect(play.manifestHost, 'demo-local');
    expect(play.points, paidEpisode.pointPrice);
    expect(card.creditedPoints, 700);
    expect(intent.status, 'demo_paid');
    expect(walletAfter.balanceCoins, greaterThan(walletBefore.balanceCoins));
    expect(ledger.entries.map((entry) => entry.type), contains('point_card'));
    expect(deleteRequest.status, 'accepted');
  });

  test('demo transport completes email auth without secrets', () async {
    final client = TenantAdapterClient(
      baseUri: Uri.parse('https://tenant-edge.example.test'),
      transport: DemoAdapterTransport(
        flavor: FlavorConfig.coolshow(),
        endUserRef: 'anon:coolshow-demo-device',
      ),
    );

    final started = await client.startEmailAuth(
      email: 'demo@example.com',
      endUserRef: 'anon:coolshow-demo-device',
    );
    final verified = await client.verifyEmailAuth(
      challengeId: started.challengeId,
      code: '123456',
      endUserRef: 'anon:coolshow-demo-device',
    );

    expect(started.emailMasked, 'd...@example.com');
    expect(verified.account.membershipTier, 'registered');
    expect(verified.account.authProviders, ['email']);
  });
}
