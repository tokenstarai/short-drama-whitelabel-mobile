import 'dart:convert';
import 'dart:io';

import 'app_models.dart';

abstract class AdapterTransport {
  Future<AdapterResponse> send(AdapterRequest request);
}

class AdapterRequest {
  const AdapterRequest({
    required this.method,
    required this.path,
    this.headers = const {},
    this.body,
  });

  final String method;
  final String path;
  final Map<String, String> headers;
  final Map<String, dynamic>? body;
}

class AdapterResponse {
  const AdapterResponse({required this.statusCode, required this.body});

  final int statusCode;
  final String body;
}

class HttpClientAdapterTransport implements AdapterTransport {
  HttpClientAdapterTransport(this.baseUri);

  final Uri baseUri;

  @override
  Future<AdapterResponse> send(AdapterRequest request) async {
    final uri = baseUri.resolve(request.path);
    final httpClient = HttpClient();
    final httpRequest = await httpClient.openUrl(request.method, uri);
    httpRequest.headers.set('content-type', 'application/json; charset=utf-8');
    for (final entry in request.headers.entries) {
      httpRequest.headers.set(entry.key, entry.value);
    }
    if (request.body != null) {
      httpRequest.write(jsonEncode(request.body));
    }
    final response = await httpRequest.close();
    final body = await response.transform(utf8.decoder).join();
    httpClient.close();
    return AdapterResponse(statusCode: response.statusCode, body: body);
  }
}

class TenantAdapterClient {
  TenantAdapterClient({required this.baseUri, AdapterTransport? transport})
      : transport = transport ?? HttpClientAdapterTransport(baseUri);

  final Uri baseUri;
  final AdapterTransport transport;

  Future<AppConfig> fetchConfig() async {
    final json = await _sendJson(
      const AdapterRequest(method: 'GET', path: '/config'),
    );
    return AppConfig.fromJson(json);
  }

  Future<List<CatalogDrama>> fetchCatalog() async {
    final json = await _sendJson(
      const AdapterRequest(method: 'GET', path: '/catalog'),
    );
    final items = json['items'] as List<dynamic>;
    return items
        .map((item) => CatalogDrama.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<DramaDetail> fetchDrama(String dramaId) async {
    final json = await _sendJson(
      AdapterRequest(method: 'GET', path: '/dramas/$dramaId'),
    );
    return DramaDetail.fromJson(json);
  }

  Future<PlayAuthorization> authorizePlayback({
    required String dramaId,
    required String episodeId,
    required String endUserRef,
    required String idempotencyKey,
  }) async {
    final json = await _sendJson(
      AdapterRequest(
        method: 'POST',
        path: '/play',
        headers: {'idempotency-key': idempotencyKey},
        body: {
          'dramaId': dramaId,
          'episodeId': episodeId,
          'endUserRef': endUserRef,
          'clientContext': {
            'platform': Platform.operatingSystem,
            'appVersion': '0.1.0',
          },
        },
      ),
    );
    return PlayAuthorization.fromJson(json);
  }

  Future<ConsumerWallet> fetchWallet({String? deviceId}) async {
    final json = await _sendJson(
      AdapterRequest(
        method: 'GET',
        path: '/wallet',
        headers: {if (deviceId != null) 'x-device-id': deviceId},
      ),
    );
    return ConsumerWallet.fromJson(json);
  }

  Future<PaymentOptions> fetchPaymentOptions() async {
    final json = await _sendJson(
      const AdapterRequest(method: 'GET', path: '/payment/options'),
    );
    return PaymentOptions.fromJson(json);
  }

  Future<TopupPaymentChannels> fetchTopupPaymentChannels() async {
    final json = await _sendJson(
      const AdapterRequest(method: 'GET', path: '/topups/payment-channels'),
    );
    return TopupPaymentChannels.fromJson(json);
  }

  Future<WalletLedger> fetchWalletLedger({String? deviceId}) async {
    final json = await _sendJson(
      AdapterRequest(
        method: 'GET',
        path: '/wallet/ledger',
        headers: {if (deviceId != null) 'x-device-id': deviceId},
      ),
    );
    return WalletLedger.fromJson(json);
  }

  Future<PaymentIntentResult> createPaymentIntent({
    required String provider,
    required String packageId,
    required int amountOriginal,
    required String currency,
    required String endUserRef,
    required String idempotencyKey,
  }) async {
    final json = await _sendJson(
      AdapterRequest(
        method: 'POST',
        path: '/payment/intents',
        headers: {'idempotency-key': idempotencyKey},
        body: {
          'provider': provider,
          'packageId': packageId,
          'amountOriginal': amountOriginal,
          'currency': currency,
          'endUserRef': endUserRef,
        },
      ),
    );
    return PaymentIntentResult.fromJson(json);
  }

  Future<PaymentIntentResult> verifyStorePurchase({
    required String provider,
    required String packageId,
    required String productId,
    required String transactionId,
    required String purchaseToken,
    required String verificationData,
    required String verificationSource,
    required String endUserRef,
    required String idempotencyKey,
  }) async {
    final json = await _sendJson(
      AdapterRequest(
        method: 'POST',
        path: '/payment/store-purchases/verify',
        headers: {'idempotency-key': idempotencyKey},
        body: {
          'provider': provider,
          'packageId': packageId,
          'productId': productId,
          'transactionId': transactionId,
          'purchaseToken': purchaseToken,
          'verificationData': verificationData,
          'verificationSource': verificationSource,
          'endUserRef': endUserRef,
        },
      ),
    );
    return PaymentIntentResult.fromJson(json);
  }

  Future<EmailAuthStartResult> startEmailAuth({
    required String email,
    String? endUserRef,
  }) async {
    final json = await _sendJson(
      AdapterRequest(
        method: 'POST',
        path: '/auth/email/start',
        body: {
          'email': email,
          if (endUserRef != null) 'endUserRef': endUserRef,
        },
      ),
    );
    return EmailAuthStartResult.fromJson(json);
  }

  Future<EmailAuthVerifyResult> verifyEmailAuth({
    required String challengeId,
    required String code,
    required String endUserRef,
  }) async {
    final json = await _sendJson(
      AdapterRequest(
        method: 'POST',
        path: '/auth/email/verify',
        headers: {'x-device-id': endUserRef},
        body: {
          'challengeId': challengeId,
          'code': code,
          'endUserRef': endUserRef,
        },
      ),
    );
    return EmailAuthVerifyResult.fromJson(json);
  }

  Future<OAuthStartResult> startOAuth({
    required String provider,
    String? endUserRef,
  }) async {
    final json = await _sendJson(
      AdapterRequest(
        method: 'POST',
        path: '/auth/oauth/$provider/start',
        body: {
          if (endUserRef != null) 'endUserRef': endUserRef,
        },
      ),
    );
    return OAuthStartResult.fromJson(json);
  }

  Future<OAuthCompleteResult> completeOAuth({
    required String provider,
    required String oauthStartId,
    required String code,
    String? state,
    required String endUserRef,
  }) async {
    final json = await _sendJson(
      AdapterRequest(
        method: 'POST',
        path: '/auth/oauth/$provider/complete',
        headers: {'x-device-id': endUserRef},
        body: {
          'oauthStartId': oauthStartId,
          'code': code,
          if (state != null && state.isNotEmpty) 'state': state,
          'endUserRef': endUserRef,
        },
      ),
    );
    return OAuthCompleteResult.fromJson(json);
  }

  Future<UserAccount> fetchMe({String? deviceId}) async {
    final json = await _sendJson(
      AdapterRequest(
        method: 'GET',
        path: '/me',
        headers: {if (deviceId != null) 'x-device-id': deviceId},
      ),
    );
    return UserAccount.fromJson(json);
  }

  Future<CardRedeemResult> redeemConsumerCard({
    required String cardCode,
    required String endUserRef,
    required String idempotencyKey,
  }) async {
    final json = await _sendJson(
      AdapterRequest(
        method: 'POST',
        path: '/payment/card-redeem',
        headers: {'idempotency-key': idempotencyKey},
        body: {'cardCode': cardCode, 'endUserRef': endUserRef},
      ),
    );
    return CardRedeemResult.fromJson({
      'requestId': json['requestId'],
      'status': json['status'],
      'creditedPoints': json['creditedCoins'] ?? json['creditedPoints'] ?? 0,
      'balanceAfter': json['balanceAfter'] ?? 0,
    });
  }

  Future<OfflineTopupApplicationResult> submitConsumerOfflineApplication({
    required String provider,
    required int amountOriginal,
    required String currency,
    required int requestedCoins,
    required String endUserRef,
    required String idempotencyKey,
    String? paymentChannelId,
    String? proofR2Key,
  }) async {
    final json = await _sendJson(
      AdapterRequest(
        method: 'POST',
        path: '/payment/offline-applications',
        headers: {'idempotency-key': idempotencyKey},
        body: {
          'provider': provider,
          'amountOriginal': amountOriginal,
          'currency': currency,
          'requestedPoints': requestedCoins,
          'requestedBy': endUserRef,
          if (paymentChannelId != null) 'paymentChannelId': paymentChannelId,
          if (proofR2Key != null) 'proofR2Key': proofR2Key,
        },
      ),
    );
    return OfflineTopupApplicationResult.fromJson({
      'requestId': json['requestId'],
      'status': json['status'],
      'applicationId': json['applicationId'],
      'requestedPoints': json['requestedCoins'] ?? json['requestedPoints'] ?? 0,
    });
  }

  Future<CardRedeemResult> redeemCard({
    required String cardCode,
    required String idempotencyKey,
  }) async {
    final json = await _sendJson(
      AdapterRequest(
        method: 'POST',
        path: '/cards/redeem',
        headers: {'idempotency-key': idempotencyKey},
        body: {'cardCode': cardCode},
      ),
    );
    return CardRedeemResult.fromJson(json);
  }

  Future<OfflineTopupApplicationResult> submitOfflineTopup({
    required int amountOriginal,
    required String currency,
    required int requestedPoints,
    required String idempotencyKey,
    String? paymentChannelId,
    String? proofR2Key,
    String? requestedBy,
  }) async {
    final json = await _sendJson(
      AdapterRequest(
        method: 'POST',
        path: '/topups/offline-applications',
        headers: {'idempotency-key': idempotencyKey},
        body: {
          'amountOriginal': amountOriginal,
          'currency': currency,
          'requestedPoints': requestedPoints,
          if (paymentChannelId != null) 'paymentChannelId': paymentChannelId,
          if (proofR2Key != null) 'proofR2Key': proofR2Key,
          if (requestedBy != null) 'requestedBy': requestedBy,
        },
      ),
    );
    return OfflineTopupApplicationResult.fromJson(json);
  }

  Future<FeedbackResult> submitFeedback({
    String category = 'general',
    String? message,
    String? dramaId,
    String? episodeId,
    String? endUserRef,
  }) async {
    final json = await _sendJson(
      AdapterRequest(
        method: 'POST',
        path: '/feedback',
        body: {
          'category': category,
          if (message != null) 'message': message,
          if (dramaId != null) 'dramaId': dramaId,
          if (episodeId != null) 'episodeId': episodeId,
          if (endUserRef != null) 'endUserRef': endUserRef,
        },
      ),
    );
    return FeedbackResult.fromJson(json);
  }

  Future<AccountDeletionRequestResult> submitAccountDelete({
    required String accountRef,
  }) async {
    final json = await _sendJson(
      AdapterRequest(
        method: 'POST',
        path: '/me/delete-request',
        body: {'accountRef': accountRef},
      ),
    );
    return AccountDeletionRequestResult.fromJson(json);
  }

  Future<Map<String, dynamic>> _sendJson(AdapterRequest request) async {
    final response = await transport.send(request);
    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    if (response.statusCode >= 400) {
      final error = decoded['error'] as Map<String, dynamic>;
      throw AppApiException(
        code: error['code'] as String,
        message: error['message'] as String,
        requestId: error['requestId'] as String,
      );
    }
    return decoded;
  }
}
