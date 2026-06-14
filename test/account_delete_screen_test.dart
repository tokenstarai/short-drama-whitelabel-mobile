import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:short_drama_whitelabel/app/app_runtime.dart';
import 'package:short_drama_whitelabel/core/api/tenant_adapter_client.dart';
import 'package:short_drama_whitelabel/features/account_delete/account_delete_screen.dart';
import 'package:short_drama_whitelabel/flavor/flavor.dart';

class AccountDeleteFakeTransport implements AdapterTransport {
  final List<AdapterRequest> requests = [];

  @override
  Future<AdapterResponse> send(AdapterRequest request) async {
    requests.add(request);
    return AdapterResponse(
      statusCode: 202,
      body: jsonEncode({
        'requestId': 'req_delete_widget',
        'status': 'accepted',
        'deletionRequestId': 'delete_widget',
        'accountRefMasked': 'anon:g...vice',
      }),
    );
  }
}

void main() {
  testWidgets('account deletion defaults to runtime end-user reference', (
    tester,
  ) async {
    final transport = AccountDeleteFakeTransport();
    final flavor = FlavorConfig.hongguo();
    final runtime = AppRuntime(
      flavor: flavor,
      endUserRef: 'anon:goldfruit-install-delete',
      client: TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      ),
    );
    addTearDown(runtime.dispose);

    await tester.pumpWidget(
      AppRuntimeScope(
        runtime: runtime,
        child: MaterialApp(home: AccountDeleteScreen(flavor: flavor)),
      ),
    );

    expect(
      find.widgetWithText(TextField, 'anon:goldfruit-install-delete'),
      findsOneWidget,
    );

    await tester.tap(find.text('Submit request'));
    await tester.pumpAndSettle();

    expect(transport.requests.single.path, '/me/delete-request');
    expect(
      transport.requests.single.body?['accountRef'],
      'anon:goldfruit-install-delete',
    );
  });
}
