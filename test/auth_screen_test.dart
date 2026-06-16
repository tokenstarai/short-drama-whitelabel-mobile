import 'dart:convert';
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:short_drama_whitelabel/app/app_runtime.dart';
import 'package:short_drama_whitelabel/core/api/tenant_adapter_client.dart';
import 'package:short_drama_whitelabel/features/auth/auth_screen.dart';
import 'package:short_drama_whitelabel/flavor/flavor.dart';

class AuthFakeTransport implements AdapterTransport {
  final List<AdapterRequest> requests = [];

  @override
  Future<AdapterResponse> send(AdapterRequest request) async {
    requests.add(request);
    if (request.path == '/auth/email/start') {
      return _ok({
        'requestId': 'req_email_widget',
        'status': 'accepted',
        'provider': 'email',
        'challengeId': 'email_widget',
        'emailMasked': 'u...e@example.com',
      }, statusCode: 202);
    }
    if (request.path == '/auth/email/verify') {
      return _ok({
        'requestId': 'req_email_verify_widget',
        'status': 'verified',
        'provider': 'email',
        'account': {
          'tenantId': 'tenant_widget',
          'accountRefMasked': 'anon:a...dget',
          'authProviders': ['email', 'google'],
          'membershipTier': 'registered',
          'deletionEndpoint': '/me/delete-request',
        },
      });
    }
    if (request.path == '/auth/oauth/google/start') {
      return _ok({
        'requestId': 'req_oauth_widget',
        'status': 'ready',
        'provider': 'google',
        'oauthStartId': 'oauth_widget',
        'tenantId': 'tenant_widget',
        'authUrl':
            'https://tenant.example.test/auth/oauth/google/authorize?oauthStartId=oauth_widget',
      });
    }
    if (request.path == '/auth/oauth/google/complete') {
      return _ok({
        'requestId': 'req_oauth_complete_widget',
        'status': 'verified',
        'provider': 'google',
        'account': {
          'tenantId': 'tenant_widget',
          'accountRefMasked': 'anon:o...dget',
          'authProviders': ['email', 'google'],
          'membershipTier': 'registered',
          'deletionEndpoint': '/me/delete-request',
        },
      });
    }
    throw StateError('Unexpected request: ${request.path}');
  }
}

class AuthErrorTransport implements AdapterTransport {
  final List<AdapterRequest> requests = [];

  @override
  Future<AdapterResponse> send(AdapterRequest request) async {
    requests.add(request);
    return const AdapterResponse(
      statusCode: 403,
      body: '''
        {
          "error": {
            "code": "APP_AUTH_PROVIDER_DISABLED",
            "message": "Email login is disabled for this tenant.",
            "requestId": "req_auth_raw"
          }
        }
      ''',
    );
  }
}

class TestOAuthCallbackLinks implements OAuthCallbackLinks {
  TestOAuthCallbackLinks({Uri? initialLink})
      : _initialLink = Future.value(initialLink);

  final Future<Uri?> _initialLink;
  final controller = StreamController<Uri>.broadcast();

  @override
  Future<Uri?> getInitialLink() => _initialLink;

  @override
  Stream<Uri> get uriLinkStream => controller.stream;

  Future<void> dispose() => controller.close();
}

AdapterResponse _ok(Map<String, dynamic> body, {int statusCode = 200}) {
  return AdapterResponse(statusCode: statusCode, body: jsonEncode(body));
}

void main() {
  testWidgets('email verification updates runtime account state', (
    tester,
  ) async {
    final flavor = FlavorConfig.douyin();
    final transport = AuthFakeTransport();
    final runtime = AppRuntime(
      flavor: flavor,
      endUserRef: 'anon:pulsedrama-auth-widget',
      client: TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      ),
    );
    addTearDown(runtime.dispose);

    await tester.pumpWidget(
      AppRuntimeScope(
        runtime: runtime,
        child: MaterialApp(home: AuthScreen(flavor: flavor)),
      ),
    );

    await tester.tap(find.text('Continue with email'));
    await tester.pumpAndSettle();
    await tester.drag(find.byType(ListView), const Offset(0, -360));
    await tester.pumpAndSettle();
    expect(find.textContaining('Email challenge email_widget'), findsOneWidget);

    await tester.drag(find.byType(ListView), const Offset(0, -160));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('email-verification-code-input')),
      '654321',
    );
    await tester.tap(find.text('Verify email'));
    await tester.pumpAndSettle();

    expect(runtime.account?.accountRefMasked, 'anon:a...dget');
    expect(runtime.account?.membershipTier, 'registered');
    expect(find.textContaining('Email verified for anon:a...dget'),
        findsOneWidget);
    expect(transport.requests.map((request) => request.path), [
      '/auth/email/start',
      '/auth/email/verify',
    ]);
    expect(
      transport.requests.first.body?['endUserRef'],
      'anon:pulsedrama-auth-widget',
    );
    expect(
      transport.requests.last.body?['endUserRef'],
      'anon:pulsedrama-auth-widget',
    );
    expect(transport.requests.last.body?['code'], '654321');
  });

  testWidgets('social login opens tenant hosted oauth url without app secrets',
      (
    tester,
  ) async {
    final flavor = FlavorConfig.douyin();
    final transport = AuthFakeTransport();
    final launched = <Uri>[];
    final runtime = AppRuntime(
      flavor: flavor,
      endUserRef: 'anon:pulsedrama-oauth-widget',
      client: TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      ),
    );
    addTearDown(runtime.dispose);

    await tester.pumpWidget(
      AppRuntimeScope(
        runtime: runtime,
        child: MaterialApp(
          home: AuthScreen(
            flavor: flavor,
            launchOAuthUrl: (uri) async {
              launched.add(uri);
              return true;
            },
          ),
        ),
      ),
    );

    await tester.tap(find.text('Continue with google'));
    await tester.pumpAndSettle();

    expect(
      launched.single.toString(),
      'https://tenant.example.test/auth/oauth/google/authorize?oauthStartId=oauth_widget',
    );
    expect(find.textContaining('google sign-in opened'), findsOneWidget);
    expect(transport.requests.single.path, '/auth/oauth/google/start');
    expect(
      transport.requests.single.body?['endUserRef'],
      'anon:pulsedrama-oauth-widget',
    );
    expect(jsonEncode(transport.requests.single.body).toLowerCase(),
        isNot(contains('secret')));
  });

  testWidgets('social login completion updates runtime account state', (
    tester,
  ) async {
    final flavor = FlavorConfig.douyin();
    final transport = AuthFakeTransport();
    final runtime = AppRuntime(
      flavor: flavor,
      endUserRef: 'anon:pulsedrama-oauth-complete-widget',
      client: TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      ),
    );
    addTearDown(runtime.dispose);

    await tester.pumpWidget(
      AppRuntimeScope(
        runtime: runtime,
        child: MaterialApp(
          home: AuthScreen(
            flavor: flavor,
            launchOAuthUrl: (_) async => true,
          ),
        ),
      ),
    );

    await tester.tap(find.text('Continue with google'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(
      find.byKey(const ValueKey('oauth-callback-code-input')),
    );
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('oauth-callback-code-input')),
      'oauth-code-public',
    );
    await tester.ensureVisible(
      find.byKey(const ValueKey('oauth-callback-state-input')),
    );
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('oauth-callback-state-input')),
      'oauth-state-public',
    );
    await tester.tap(find.text('Complete google sign-in'));
    await tester.pumpAndSettle();

    expect(runtime.account?.accountRefMasked, 'anon:o...dget');
    expect(runtime.account?.membershipTier, 'registered');
    expect(find.textContaining('google verified for anon:o...dget'),
        findsOneWidget);
    expect(transport.requests.map((request) => request.path), [
      '/auth/oauth/google/start',
      '/auth/oauth/google/complete',
    ]);
    expect(
      transport.requests.last.body?['endUserRef'],
      'anon:pulsedrama-oauth-complete-widget',
    );
    expect(transport.requests.last.body?['code'], 'oauth-code-public');
    expect(transport.requests.last.body?['state'], 'oauth-state-public');
  });

  testWidgets('social login deep link callback completes account state', (
    tester,
  ) async {
    final flavor = FlavorConfig.douyin();
    final transport = AuthFakeTransport();
    final links = TestOAuthCallbackLinks();
    addTearDown(links.dispose);
    final runtime = AppRuntime(
      flavor: flavor,
      endUserRef: 'anon:pulsedrama-oauth-deeplink-widget',
      client: TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      ),
    );
    addTearDown(runtime.dispose);

    await tester.pumpWidget(
      AppRuntimeScope(
        runtime: runtime,
        child: MaterialApp(
          home: AuthScreen(
            flavor: flavor,
            callbackLinks: links,
            launchOAuthUrl: (_) async => true,
          ),
        ),
      ),
    );

    await tester.tap(find.text('Continue with google'));
    await tester.pumpAndSettle();
    links.controller.add(
      Uri.parse(
        'pulsedrama://auth?provider=google&oauthStartId=oauth_widget&code=oauth-code-deep&state=oauth-state-deep',
      ),
    );
    await tester.pumpAndSettle();

    expect(runtime.account?.accountRefMasked, 'anon:o...dget');
    expect(runtime.account?.membershipTier, 'registered');
    expect(find.textContaining('google verified for anon:o...dget'),
        findsOneWidget);
    expect(transport.requests.map((request) => request.path), [
      '/auth/oauth/google/start',
      '/auth/oauth/google/complete',
    ]);
    expect(
      transport.requests.last.body?['endUserRef'],
      'anon:pulsedrama-oauth-deeplink-widget',
    );
    expect(transport.requests.last.body?['code'], 'oauth-code-deep');
    expect(transport.requests.last.body?['state'], 'oauth-state-deep');
  });

  testWidgets('deep link callback ignores disabled oauth providers', (
    tester,
  ) async {
    final flavor = FlavorConfig.hongguo();
    final transport = AuthFakeTransport();
    final links = TestOAuthCallbackLinks();
    addTearDown(links.dispose);
    final runtime = AppRuntime(
      flavor: flavor,
      endUserRef: 'anon:goldfruit-disabled-oauth-widget',
      client: TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      ),
    );
    addTearDown(runtime.dispose);

    await tester.pumpWidget(
      AppRuntimeScope(
        runtime: runtime,
        child: MaterialApp(
          home: AuthScreen(flavor: flavor, callbackLinks: links),
        ),
      ),
    );

    links.controller.add(
      Uri.parse(
        'goldfruitdrama://auth?provider=facebook&oauthStartId=oauth_disabled&code=oauth-code-disabled&state=oauth-state-disabled',
      ),
    );
    await tester.pumpAndSettle();

    expect(runtime.account?.membershipTier, 'guest');
    expect(transport.requests, isEmpty);
    expect(
      find.textContaining('Auth provider facebook is not enabled'),
      findsOneWidget,
    );
  });

  testWidgets('auth maps Tenant Edge errors to friendly text', (
    tester,
  ) async {
    final flavor = FlavorConfig.douyin();
    final transport = AuthErrorTransport();
    final runtime = AppRuntime(
      flavor: flavor,
      endUserRef: 'anon:pulsedrama-auth-error',
      client: TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      ),
    );
    addTearDown(runtime.dispose);

    await tester.pumpWidget(
      AppRuntimeScope(
        runtime: runtime,
        child: MaterialApp(home: AuthScreen(flavor: flavor)),
      ),
    );

    await tester.tap(find.text('Continue with email'));
    await tester.pumpAndSettle();

    expect(transport.requests.single.path, '/auth/email/start');
    expect(
      find.text('Sign-in failed. Please retry or choose another method.'),
      findsOneWidget,
    );
    expect(find.textContaining('APP_AUTH_PROVIDER_DISABLED'), findsNothing);
    expect(find.textContaining('req_auth_raw'), findsNothing);
    expect(find.textContaining('Email login is disabled'), findsNothing);
  });
}
