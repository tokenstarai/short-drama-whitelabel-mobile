import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:short_drama_whitelabel/app/app_runtime.dart';
import 'package:short_drama_whitelabel/core/api/app_models.dart';
import 'package:short_drama_whitelabel/core/api/tenant_adapter_client.dart';
import 'package:short_drama_whitelabel/features/home/home_screen.dart';
import 'package:short_drama_whitelabel/flavor/flavor.dart';

class HomeNoopTransport implements AdapterTransport {
  @override
  Future<AdapterResponse> send(AdapterRequest request) async {
    return AdapterResponse(
      statusCode: 200,
      body: jsonEncode({'requestId': 'noop', 'status': 'ok'}),
    );
  }
}

AppRuntime homeRuntime(List<CatalogDrama> catalog) {
  final flavor = FlavorConfig.hongguo();
  final runtime = AppRuntime(
    flavor: flavor,
    client: TenantAdapterClient(
      baseUri: Uri.parse('https://tenant-edge.example.test'),
      transport: HomeNoopTransport(),
    ),
  );
  runtime.data = AppRuntimeData(
    catalog: catalog,
    account: runtime.data.account,
    wallet: runtime.data.wallet,
    walletLedger: runtime.data.walletLedger,
    paymentOptions: runtime.data.paymentOptions,
    topupPaymentChannels: runtime.data.topupPaymentChannels,
  );
  return runtime;
}

const homeCatalogFixtures = [
  CatalogDrama(
    dramaId: 'river',
    title: 'River Vow',
    summary: 'Cross-border romance in Jakarta.',
    posterUrl: '/posters/river.png',
    episodeCount: 24,
    readyEpisodeCount: 9,
    pointPrice: 1,
    language: 'id-ID',
    regions: ['ID'],
    tags: ['Romance'],
  ),
  CatalogDrama(
    dramaId: 'palace',
    title: 'Palace Revenge',
    summary: 'Court intrigue with daily cliffhangers.',
    posterUrl: '/posters/palace.png',
    episodeCount: 40,
    readyEpisodeCount: 18,
    pointPrice: 5,
    language: 'th-TH',
    regions: ['TH'],
    tags: ['Revenge'],
  ),
];

void main() {
  testWidgets('home search opens catalog with submitted query', (tester) async {
    final runtime = homeRuntime(homeCatalogFixtures);

    await tester.pumpWidget(
      AppRuntimeScope(
        runtime: runtime,
        child: MaterialApp(home: HomeScreen(flavor: runtime.flavor)),
      ),
    );

    await tester.enterText(find.byType(TextField), 'palace');
    await tester.testTextInput.receiveAction(TextInputAction.search);
    await tester.pumpAndSettle();

    expect(find.text('Palace Revenge'), findsWidgets);
    expect(find.text('River Vow'), findsNothing);
    expect(find.text('1 drama'), findsOneWidget);
  });
}
